"""Resource control layer (Phase 9)."""

from datetime import datetime, timezone
from typing import Dict, List, Optional
import uuid

try:
    import psutil
except Exception:
    psutil = None

from ..domain.models.resource_control import ControlAction, ControlHistory


class ResourceController:
    def __init__(self):
        self.history = ControlHistory()
        self._original_priorities = {}
        self._automatic_enabled = False

    def enable_automatic(self, enabled: bool = False):
        """Automatic control disabled by default."""
        self._automatic_enabled = bool(enabled)
        self.history = ControlHistory(
            actions=self.history.actions,
            automatic_enabled=self._automatic_enabled,
            mode="adaptive" if enabled else "recommendation",
        )

    def can_control(self, pid: int, verify_identity: bool = True) -> tuple[bool, str]:
        """Check if we can control a process safely."""
        if not self._automatic_enabled and verify_identity:
            # Still allow user-approved actions
            pass
        if psutil is None:
            return False, "psutil unavailable"
        try:
            proc = psutil.Process(pid)
            if not proc.is_running():
                return False, "Process not running"
            # Check if it's us
            if proc.pid == psutil.Process().pid:
                return False, "Cannot control own process"
            return True, "OK"
        except psutil.NoSuchProcess:
            return False, "Process does not exist"
        except psutil.AccessDenied:
            return False, "Access denied"
        except Exception as e:
            return False, str(e)

    def set_priority(self, pid: int, priority: int, reason: str, 
                     mode: str = "user_approved") -> ControlAction:
        """Set process priority with rollback support. User approval required by default."""
        action_id = str(uuid.uuid4())
        previous_state = {}
        rollback_data = {}
        
        can, msg = self.can_control(pid)
        if not can:
            action = ControlAction(
                id=action_id,
                action_type="set_priority",
                target_pid=pid,
                target_name=None,
                previous_state={},
                new_state={"priority": priority},
                reason=reason,
                mode=mode,
                reversible=True,
                rollback_data={},
                result="failed",
                error=msg,
                verified=False,
            )
            self.history.actions.append(action)
            return action

        try:
            proc = psutil.Process(pid)
            prev = proc.nice()
            previous_state = {"priority": prev}
            rollback_data = {"pid": pid, "old_priority": prev}
            self._original_priorities[(pid, proc.create_time())] = prev
            
            proc.nice(priority)
            # Verify
            new_proc = psutil.Process(pid)
            verified = new_proc.nice() == priority
            
            action = ControlAction(
                id=action_id,
                action_type="set_priority",
                target_pid=pid,
                target_name=proc.name(),
                previous_state=previous_state,
                new_state={"priority": priority},
                reason=reason,
                mode=mode,
                reversible=True,
                rollback_data=rollback_data,
                result="success" if verified else "failed",
                error=None if verified else "Verification failed",
                verified=verified,
            )
            self.history.actions.append(action)
            return action
        except Exception as e:
            action = ControlAction(
                id=action_id,
                action_type="set_priority",
                target_pid=pid,
                target_name=None,
                previous_state=previous_state,
                new_state={"priority": priority},
                reason=reason,
                mode=mode,
                reversible=True,
                rollback_data=rollback_data,
                result="failed",
                error=str(e),
                verified=False,
            )
            self.history.actions.append(action)
            return action

    def rollback(self, action_id: str) -> bool:
        """Rollback a reversible action."""
        for i, action in enumerate(self.history.actions):
            if action.id == action_id and action.reversible and action.result == "success":
                try:
                    if action.action_type == "set_priority" and action.rollback_data.get("old_priority") is not None:
                        pid = action.rollback_data["pid"]
                        proc = psutil.Process(pid)
                        proc.nice(action.rollback_data["old_priority"])
                        # Mark as rolled back
                        rolled_back = ControlAction(
                            id=str(uuid.uuid4()),
                            action_type="rollback",
                            target_pid=pid,
                            target_name=action.target_name,
                            previous_state=action.new_state,
                            new_state=action.previous_state,
                            reason=f"Rollback of {action_id}",
                            mode="user_approved",
                            reversible=False,
                            rollback_data={},
                            result="success",
                            verified=True,
                        )
                        self.history.actions.append(rolled_back)
                        return True
                except Exception:
                    return False
        return False

    def get_history(self) -> List[ControlAction]:
        return list(self.history.actions)
