"""Resource control layer (Phase 9) - corrected with identity verification."""

from datetime import datetime, timezone
from typing import Dict, List, Optional
import uuid
import os

try:
    import psutil
except Exception:
    psutil = None

from ..domain.models.resource_control import ControlAction, ControlHistory
from ..domain.models import ProcessIdentity
from .resource_control_authorization import ResourceControlAuthorizationPolicy


# Safe priority values (avoid REALTIME)
ALLOWED_PRIORITIES = {
    getattr(psutil, "IDLE_PRIORITY_CLASS", 64) if hasattr(psutil, "IDLE_PRIORITY_CLASS") else 64,
    getattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS", 16384) if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS") else 16384,
    getattr(psutil, "NORMAL_PRIORITY_CLASS", 32) if hasattr(psutil, "NORMAL_PRIORITY_CLASS") else 32,
    getattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS", 32768) if hasattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS") else 32768,
    getattr(psutil, "HIGH_PRIORITY_CLASS", 128) if hasattr(psutil, "HIGH_PRIORITY_CLASS") else 128,
}


class ResourceController:
    def __init__(self):
        self.history: List[ControlAction] = []
        self._original_priorities = {}
        self._automatic_enabled = False
        self.auth_policy = ResourceControlAuthorizationPolicy()
        self._identity_cache = {}  # key -> identity

    def enable_automatic(self, enabled: bool = False):
        """Automatic control disabled by default."""
        self._automatic_enabled = bool(enabled)

    def _verify_identity(self, identity: ProcessIdentity) -> tuple[bool, str, Optional[object]]:
        if psutil is None:
            return False, "psutil unavailable", None
        try:
            proc = psutil.Process(identity.pid)
            if not proc.is_running():
                return False, "Process not running", None
            # Revalidate PID and creation time
            create_time = proc.create_time()
            if abs(create_time - identity.create_time) > 1.0:  # Allow small drift
                return False, "Identity mismatch - PID reused or process changed", None
            # Verify it's the same process
            if proc.pid != identity.pid:
                return False, "PID changed", None
            return True, "OK", proc
        except psutil.NoSuchProcess:
            return False, "Process does not exist", None
        except psutil.AccessDenied:
            return False, "Access denied", None
        except Exception as e:
            return False, str(e), None

    def set_priority(self, identity: ProcessIdentity, priority: int, reason: str,
                     mode: str = "user_approved", user_confirmed: bool = False,
                     classification: Optional[Dict] = None,
                     is_foreground: bool = False) -> ControlAction:
        action_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc)

        # Authorization
        auth = self.auth_policy.authorize_priority_change(
            identity, classification=classification,
            is_foreground=is_foreground,
            user_confirmed=user_confirmed,
            automatic_enabled=self._automatic_enabled,
            mode=mode
        )
        if not auth.allowed:
            action = ControlAction(
                id=action_id,
                action_type="set_priority",
                target_pid=identity.pid,
                target_name=identity.name,
                previous_state={},
                new_state={"priority": priority},
                reason=reason,
                mode=mode,
                reversible=True,
                rollback_data={"identity": identity, "reason": auth.reason},
                timestamp=timestamp,
                result="failed",
                error=f"Auth denied: {auth.code} - {auth.reason}",
                verified=False,
                metadata={"confirmation_status": user_confirmed, "executable": identity.exe},
            )
            self.history.append(action)
            return action

        # Reject REALTIME and aggressive changes
        try:
            realtime = getattr(psutil, "REALTIME_PRIORITY_CLASS", None)
            if realtime is not None and priority == realtime:
                action = ControlAction(
                    id=action_id,
                    action_type="set_priority",
                    target_pid=identity.pid,
                    target_name=identity.name,
                    previous_state={},
                    new_state={"priority": priority},
                    reason=reason,
                    mode=mode,
                    reversible=True,
                    rollback_data={"identity": identity},
                    timestamp=timestamp,
                    result="failed",
                    error="REALTIME priority not allowed",
                    verified=False,
                    metadata={"confirmation_status": user_confirmed},
                )
                self.history.append(action)
                return action
        except Exception:
            pass

        # Identity verification
        verified, msg, proc = self._verify_identity(identity)
        if not verified or proc is None:
            action = ControlAction(
                id=action_id,
                action_type="set_priority",
                target_pid=identity.pid,
                target_name=identity.name,
                previous_state={},
                new_state={"priority": priority},
                reason=reason,
                mode=mode,
                reversible=True,
                rollback_data={"identity": identity},
                timestamp=timestamp,
                result="failed",
                error=f"Identity verification failed: {msg}",
                verified=False,
                metadata={"confirmation_status": user_confirmed, "executable": identity.exe},
            )
            self.history.append(action)
            return action

        try:
            prev = proc.nice()
            previous_state = {"priority": prev}
            rollback_data = {
                "identity": identity,
                "old_priority": prev,
                "pid": identity.pid,
                "create_time": identity.create_time,
            }
            self._identity_cache[identity.key] = identity

            proc.nice(priority)
            # Verify
            new_proc = psutil.Process(identity.pid)
            # Recheck identity
            v2, _, _ = self._verify_identity(identity)
            new_priority = new_proc.nice()
            verified_applied = (new_priority == priority) and v2

            action = ControlAction(
                id=action_id,
                action_type="set_priority",
                target_pid=identity.pid,
                target_name=identity.name,
                previous_state=previous_state,
                new_state={"priority": priority},
                reason=reason,
                mode=mode,
                reversible=True,
                rollback_data=rollback_data,
                timestamp=timestamp,
                result="success" if verified_applied else "failed",
                error=None if verified_applied else "Verification failed - priority not applied or identity changed",
                verified=verified_applied,
                metadata={"confirmation_status": user_confirmed, "executable": identity.exe},
            )
            self.history.append(action)
            return action
        except psutil.AccessDenied:
            action = ControlAction(
                id=action_id,
                action_type="set_priority",
                target_pid=identity.pid,
                target_name=identity.name,
                previous_state={},
                new_state={"priority": priority},
                reason=reason,
                mode=mode,
                reversible=True,
                rollback_data={"identity": identity},
                timestamp=timestamp,
                result="failed",
                error="Permission denied",
                verified=False,
                metadata={"confirmation_status": user_confirmed},
            )
            self.history.append(action)
            return action
        except Exception as e:
            action = ControlAction(
                id=action_id,
                action_type="set_priority",
                target_pid=identity.pid,
                target_name=identity.name,
                previous_state={},
                new_state={"priority": priority},
                reason=reason,
                mode=mode,
                reversible=True,
                rollback_data={"identity": identity},
                timestamp=timestamp,
                result="failed",
                error=str(e),
                verified=False,
                metadata={"confirmation_status": user_confirmed},
            )
            self.history.append(action)
            return action

    def rollback(self, action_id: str) -> tuple[bool, str]:
        for action in self.history:
            if action.id == action_id:
                if not action.reversible or action.result != "success":
                    return False, "Action not reversible or not successful"
                rb = action.rollback_data
                identity = rb.get("identity")
                if not isinstance(identity, ProcessIdentity):
                    return False, "No original identity stored"
                # Revalidate identity
                verified, msg, proc = self._verify_identity(identity)
                if not verified or proc is None:
                    return False, f"Identity changed - cannot rollback safely: {msg}"
                old_priority = rb.get("old_priority")
                if old_priority is None:
                    return False, "No original priority recorded"
                try:
                    proc.nice(old_priority)
                    # Verify
                    v2, _, proc2 = self._verify_identity(identity)
                    if not v2:
                        return False, "Identity changed during rollback"
                    if proc2.nice() != old_priority:
                        return False, "Rollback verification failed - priority not restored"
                    rolled_back = ControlAction(
                        id=str(uuid.uuid4()),
                        action_type="rollback",
                        target_pid=identity.pid,
                        target_name=identity.name,
                        previous_state=action.new_state,
                        new_state=action.previous_state,
                        reason=f"Rollback of {action_id}",
                        mode="user_approved",
                        reversible=False,
                        rollback_data={"original_action": action_id},
                        timestamp=datetime.now(timezone.utc),
                        result="success",
                        verified=True,
                        metadata={"confirmation_status": True, "executable": identity.exe},
                    )
                    self.history.append(rolled_back)
                    return True, "Rolled back successfully"
                except psutil.AccessDenied:
                    return False, "Permission denied during rollback"
                except Exception as e:
                    return False, str(e)
        return False, "Action not found"

    def get_history(self) -> List[ControlAction]:
        return list(self.history)
