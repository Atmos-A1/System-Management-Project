"""Identity-verified, opt-in Windows process priority control.

The controller fails closed on non-Windows systems. Every mutation is performed
through one Windows process handle after its creation time has been verified.
No process is terminated, suspended, or assigned CPU affinity.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Dict, List, Optional
import uuid

from ..config import config
from ..domain.models import ProcessIdentity
from ..domain.models.resource_control import ControlAction
from .resource_control_authorization import ResourceControlAuthorizationPolicy

try:
    import psutil
except Exception:  # pragma: no cover - optional dependency guard
    psutil = None


# Conservative V1 allowlist. NORMAL is included for restoration; no priority
# above normal can be newly requested by Panther.
ALLOWED_PRIORITIES = {
    getattr(psutil, "IDLE_PRIORITY_CLASS", 0x40) if psutil else 0x40,
    getattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS", 0x4000) if psutil else 0x4000,
    getattr(psutil, "NORMAL_PRIORITY_CLASS", 0x20) if psutil else 0x20,
}


class WindowsPriorityAdapter:
    """Change and verify priority through the same process handle."""

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_SET_INFORMATION = 0x0200
    FILETIME_EPOCH_OFFSET = 11644473600

    def change_priority(self, identity: ProcessIdentity, priority: int, prevent_foreground: bool = False):
        if os.name != "nt":
            return False, "Priority control is available only on Windows", None, None

        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetPriorityClass.argtypes = [wintypes.HANDLE]
        kernel32.GetPriorityClass.restype = wintypes.DWORD
        kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetPriorityClass.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        access = self.PROCESS_QUERY_LIMITED_INFORMATION | self.PROCESS_SET_INFORMATION
        handle = kernel32.OpenProcess(access, False, identity.pid)
        if not handle:
            return False, "OpenProcess failed: {}".format(ctypes.get_last_error()), None, None

        previous = None
        try:
            creation, exit_time, kernel_time, user_time = (
                wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
            )
            if not kernel32.GetProcessTimes(
                handle, ctypes.byref(creation), ctypes.byref(exit_time),
                ctypes.byref(kernel_time), ctypes.byref(user_time)
            ):
                return False, "GetProcessTimes failed: {}".format(ctypes.get_last_error()), None, None

            ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            actual_create_time = ticks / 10_000_000 - self.FILETIME_EPOCH_OFFSET
            if abs(actual_create_time - identity.create_time) > 0.02:
                return False, "Process identity changed (PID reuse or creation-time mismatch)", None, None

            if prevent_foreground:
                kernel32.GetForegroundWindow.restype = wintypes.HWND
                kernel32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
                foreground = kernel32.GetForegroundWindow()
                if foreground:
                    foreground_pid = wintypes.DWORD()
                    thread_id = kernel32.GetWindowThreadProcessId(foreground, ctypes.byref(foreground_pid))
                    if not thread_id:
                        return False, "Could not verify foreground process; automatic control refused", None, None
                    if foreground_pid.value == identity.pid:
                        return False, "Foreground application is protected from automatic control", None, None

            previous = int(kernel32.GetPriorityClass(handle))
            if not previous:
                return False, "GetPriorityClass failed: {}".format(ctypes.get_last_error()), None, None

            if not kernel32.SetPriorityClass(handle, int(priority)):
                return False, "SetPriorityClass failed: {}".format(ctypes.get_last_error()), previous, None

            # Verify identity and resulting state using the same still-open handle.
            if not kernel32.GetProcessTimes(
                handle, ctypes.byref(creation), ctypes.byref(exit_time),
                ctypes.byref(kernel_time), ctypes.byref(user_time)
            ):
                return False, "Could not re-verify process identity", previous, None
            ticks_after = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            time_after = ticks_after / 10_000_000 - self.FILETIME_EPOCH_OFFSET
            actual = int(kernel32.GetPriorityClass(handle))
            if abs(time_after - identity.create_time) > 0.02 or actual != int(priority):
                return False, "Priority or process identity verification failed", previous, actual
            return True, "Priority change verified", previous, actual
        finally:
            kernel32.CloseHandle(handle)


class ResourceController:
    def __init__(self, db_path: Optional[Path] = None, process_adapter=None,
                 authorization_policy=None):
        self.db_path = Path(db_path or config.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.process_adapter = process_adapter or WindowsPriorityAdapter()
        self.auth_policy = authorization_policy or ResourceControlAuthorizationPolicy()
        self._automatic_enabled = False
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS resource_control_actions (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    action_json TEXT NOT NULL
                )
            """)

    def enable_automatic(self, enabled: bool = False):
        """Enable only after an explicit caller action; remains off by default."""
        self._automatic_enabled = bool(enabled)

    @property
    def history(self) -> List[ControlAction]:
        return self.get_history()

    @staticmethod
    def _serialize_value(value):
        if isinstance(value, ProcessIdentity):
            return {"__type__": "ProcessIdentity", "pid": value.pid,
                    "create_time": value.create_time, "name": value.name, "exe": value.exe}
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(k): ResourceController._serialize_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [ResourceController._serialize_value(v) for v in value]
        return value

    @staticmethod
    def _deserialize_value(value):
        if isinstance(value, dict):
            if value.get("__type__") == "ProcessIdentity":
                return ProcessIdentity(value["pid"], value["create_time"], value["name"], value.get("exe"))
            return {k: ResourceController._deserialize_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [ResourceController._deserialize_value(v) for v in value]
        return value

    def _record(self, action: ControlAction) -> ControlAction:
        payload = {
            "id": action.id, "action_type": action.action_type,
            "target_pid": action.target_pid, "target_name": action.target_name,
            "previous_state": self._serialize_value(action.previous_state),
            "new_state": self._serialize_value(action.new_state), "reason": action.reason,
            "mode": action.mode, "reversible": action.reversible,
            "rollback_data": self._serialize_value(action.rollback_data),
            "timestamp": action.timestamp.isoformat(), "result": action.result,
            "error": action.error, "verified": action.verified,
            "confirmation_status": action.confirmation_status,
            "identity_key": list(action.identity_key) if action.identity_key else None,
            "executable": action.executable,
            "metadata": self._serialize_value(action.metadata),
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO resource_control_actions (id, timestamp, action_json) VALUES (?, ?, ?)",
                (action.id, action.timestamp.isoformat(), json.dumps(payload)),
            )
        return action

    def _make_action(self, identity, priority, reason, mode, confirmed, result,
                     error=None, previous=None, rollback=None, verified=False):
        return self._record(ControlAction(
            id=str(uuid.uuid4()), action_type="set_priority",
            target_pid=identity.pid, target_name=identity.name,
            previous_state=previous or {}, new_state={"priority": priority},
            reason=reason, mode=mode, reversible=bool(verified and rollback),
            rollback_data=rollback or {}, timestamp=datetime.now(timezone.utc),
            result=result, error=error, verified=verified,
            confirmation_status=bool(confirmed), identity_key=identity.key,
            executable=identity.exe,
            metadata={"confirmation_status": bool(confirmed), "executable": identity.exe},
        ))

    def set_priority(self, identity: ProcessIdentity, priority: int, reason: str,
                     mode: str = "user_approved", user_confirmed: bool = False,
                     classification: Optional[Dict] = None,
                     is_foreground: bool = False) -> ControlAction:
        if not isinstance(identity, ProcessIdentity):
            raise TypeError("identity must be a ProcessIdentity")
        if isinstance(priority, bool) or not isinstance(priority, int) or priority not in ALLOWED_PRIORITIES:
            return self._make_action(identity, priority, reason, mode, user_confirmed,
                                     "failed", "Requested priority is outside the conservative V1 allowlist")

        auth = self.auth_policy.authorize_priority_change(
            identity, classification=classification, is_foreground=is_foreground,
            user_confirmed=user_confirmed, automatic_enabled=self._automatic_enabled, mode=mode
        )
        if not auth.allowed:
            return self._make_action(identity, priority, reason, mode, user_confirmed,
                                     "rejected", "Authorization denied: {} - {}".format(auth.code, auth.reason))

        try:
            ok, message, previous, actual = self.process_adapter.change_priority(
                identity, priority, prevent_foreground=(mode == "automatic")
            )
        except Exception as exc:
            ok, message, previous, actual = False, "Priority adapter failed: {}".format(exc), None, None
        if not ok:
            return self._make_action(identity, priority, reason, mode, user_confirmed,
                                     "failed", message, previous={"priority": previous} if previous is not None else {})
        if actual != priority:
            return self._make_action(identity, priority, reason, mode, user_confirmed,
                                     "failed", "Priority verification mismatch",
                                     previous={"priority": previous} if previous is not None else {})
        rollback = {"identity": identity, "old_priority": previous}
        return self._make_action(identity, priority, reason, mode, user_confirmed,
                                 "success", None, previous={"priority": previous},
                                 rollback=rollback, verified=True)

    def rollback(self, action_id: str, user_confirmed: bool = False) -> tuple[bool, str]:
        if not user_confirmed:
            return False, "Explicit confirmation is required to roll back a priority change"
        action = next((a for a in self.get_history() if a.id == action_id), None)
        if action is None:
            return False, "Action not found"
        if not action.reversible or action.result != "success":
            return False, "Action is not reversible or was not successful"
        identity = action.rollback_data.get("identity")
        old_priority = action.rollback_data.get("old_priority")
        if not isinstance(identity, ProcessIdentity) or old_priority is None:
            return False, "Original process identity or priority is unavailable"
        try:
            ok, message, previous, actual = self.process_adapter.change_priority(identity, old_priority)
        except Exception as exc:
            ok, message, previous, actual = False, "Rollback adapter failed: {}".format(exc), None, None
        if not ok or actual != old_priority:
            rollback_action = ControlAction(
                id=str(uuid.uuid4()), action_type="rollback", target_pid=identity.pid,
                target_name=identity.name, previous_state={"priority": previous},
                new_state={"priority": old_priority}, reason="Rollback of {}".format(action_id),
                mode="user_approved", reversible=False, rollback_data={"original_action": action_id},
                timestamp=datetime.now(timezone.utc), result="failed",
                error=message or "Rollback verification failed", verified=False,
                confirmation_status=True, identity_key=identity.key, executable=identity.exe,
            )
            self._record(rollback_action)
            return False, rollback_action.error
        rollback_action = ControlAction(
            id=str(uuid.uuid4()), action_type="rollback", target_pid=identity.pid,
            target_name=identity.name, previous_state={"priority": previous},
            new_state={"priority": old_priority}, reason="Rollback of {}".format(action_id),
            mode="user_approved", reversible=False, rollback_data={"original_action": action_id},
            timestamp=datetime.now(timezone.utc), result="success", verified=True,
            confirmation_status=True, identity_key=identity.key, executable=identity.exe,
        )
        self._record(rollback_action)
        self._mark_rolled_back(action_id)
        return True, "Rolled back successfully"

    def _mark_rolled_back(self, action_id: str):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT action_json FROM resource_control_actions WHERE id = ?", (action_id,)
            ).fetchone()
            if row is None:
                return
            data = json.loads(row["action_json"])
            data["result"] = "rolled_back"
            data["reversible"] = False
            conn.execute(
                "UPDATE resource_control_actions SET action_json = ? WHERE id = ?",
                (json.dumps(data), action_id),
            )

    def get_history(self) -> List[ControlAction]:
        with self._connect() as conn:
            rows = conn.execute("SELECT action_json FROM resource_control_actions ORDER BY timestamp, rowid").fetchall()
        actions = []
        for row in rows:
            data = json.loads(row["action_json"])
            actions.append(ControlAction(
                id=data["id"], action_type=data["action_type"], target_pid=data["target_pid"],
                target_name=data["target_name"], previous_state=self._deserialize_value(data["previous_state"]),
                new_state=self._deserialize_value(data["new_state"]), reason=data["reason"],
                mode=data["mode"], reversible=data["reversible"],
                rollback_data=self._deserialize_value(data["rollback_data"]),
                timestamp=datetime.fromisoformat(data["timestamp"]), result=data["result"],
                error=data["error"], verified=data["verified"],
                confirmation_status=data["confirmation_status"],
                identity_key=tuple(data["identity_key"]) if data["identity_key"] else None,
                executable=data["executable"], metadata=self._deserialize_value(data["metadata"]),
            ))
        return actions
