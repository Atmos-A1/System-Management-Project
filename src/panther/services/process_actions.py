"""Process action manager - safe process termination.

Implements safe termination with graceful close first, protections for critical
processes, and audit logging.
"""

import os
import signal
from typing import Dict, Any, Optional
from datetime import datetime

try:
    import psutil
except Exception:
    psutil = None

from .process_classifier import classify_process


class ProcessActionError(Exception):
    def __init__(self, message: str, error_type: str = "general"):
        super().__init__(message)
        self.error_type = error_type  # "panther_blocked", "permission_denied", "general"


class ProcessActionManager:
    def __init__(self, audit_log=None):
        self.audit_log = audit_log or []
    
    def _log_action(self, action: str, pid: int, name: str, result: str, details: str = ""):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "pid": pid,
            "name": name,
            "result": result,
            "details": details,
        }
        self.audit_log.append(entry)
        return entry
    
    def can_terminate(self, process: Dict[str, Any]) -> tuple:
        """Check if process can be terminated safely. Returns (can_terminate, reason)."""
        classification = classify_process(process)
        if not classification.get('can_terminate', False):
            reason = f"[PANTHER SAFETY BLOCK] {classification.get('explanation', 'Process is protected by Panther safety rules.')}"
            return False, reason
        return True, "Process can be terminated with caution"
    
    def graceful_close(self, pid: int) -> Dict[str, Any]:
        """Attempt graceful termination first."""
        if psutil is None:
            raise ProcessActionError("psutil required", "general")
        
        try:
            p = psutil.Process(pid)
            name = p.name()
            
            # Check if we can terminate
            proc_info = {
                'pid': pid,
                'name': name,
                'exe': p.exe() if hasattr(p, 'exe') else '',
                'ppid': p.ppid(),
            }
            can_term, reason = self.can_terminate(proc_info)
            if not can_term:
                self._log_action("graceful_close", pid, name, "blocked", reason)
                raise ProcessActionError(f"Cannot terminate: {reason}", "panther_blocked")
            
            # Try terminate() first (graceful)
            p.terminate()
            self._log_action("graceful_close", pid, name, "attempted", "Sent terminate signal")
            
            # Wait a bit for graceful exit
            try:
                gone, alive = psutil.wait_procs([p], timeout=3)
                if p in gone:
                    self._log_action("graceful_close", pid, name, "success", "Process exited gracefully")
                    return {"success": True, "message": "Process terminated gracefully"}
                else:
                    return {"success": False, "message": "Process did not exit gracefully, try force kill", "needs_force": True}
            except Exception:
                return {"success": True, "message": "Terminate signal sent"}
                
        except psutil.NoSuchProcess:
            proc_name = locals().get('name', str(pid))
            self._log_action("graceful_close", pid, proc_name, "already_gone", "Process no longer exists")
            return {"success": True, "message": "Process already terminated"}
        except psutil.AccessDenied:
            proc_name = locals().get('name', str(pid))
            self._log_action("graceful_close", pid, proc_name, "access_denied", "Windows permission denied")
            raise ProcessActionError(
                "[WINDOWS PERMISSION DENIED] Access is denied by Windows.\n\n"
                "This process requires elevated privileges to terminate.\n"
                "Options:\n"
                "  • Restart Panther as Administrator (Run as Administrator)\n"
                "  • This is normal for processes owned by other users or some system processes",
                "permission_denied"
            )
        except ProcessActionError:
            raise
        except Exception as e:
            raise ProcessActionError(f"Failed to terminate process: {e}", "general")
    
    def force_kill(self, pid: int) -> Dict[str, Any]:
        """Force kill a process (advanced action)."""
        if psutil is None:
            raise ProcessActionError("psutil required", "general")
        
        try:
            p = psutil.Process(pid)
            name = p.name()
            
            proc_info = {
                'pid': pid,
                'name': name,
                'exe': p.exe() if hasattr(p, 'exe') else '',
                'ppid': p.ppid(),
            }
            can_term, reason = self.can_terminate(proc_info)
            if not can_term:
                self._log_action("force_kill", pid, name, "blocked", reason)
                raise ProcessActionError(f"Cannot terminate: {reason}", "panther_blocked")
            
            p.kill()
            self._log_action("force_kill", pid, name, "attempted", "Sent kill signal")
            
            try:
                gone, alive = psutil.wait_procs([p], timeout=3)
                if p in gone:
                    self._log_action("force_kill", pid, name, "success", "Process killed")
                    return {"success": True, "message": "Process force killed"}
            except Exception:
                pass
            
            return {"success": True, "message": "Kill signal sent"}
                
        except psutil.NoSuchProcess:
            return {"success": True, "message": "Process already terminated"}
        except psutil.AccessDenied:
            proc_name = locals().get('name', str(pid))
            self._log_action("force_kill", pid, proc_name, "access_denied", "Windows permission denied")
            raise ProcessActionError(
                "[WINDOWS PERMISSION DENIED] Access is denied by Windows.\n\n"
                "This process requires elevated privileges to force kill.\n"
                "Options:\n"
                "  • Restart Panther as Administrator (Run as Administrator)\n"
                "  • This is normal for processes owned by other users or some system processes",
                "permission_denied"
            )
        except ProcessActionError:
            raise
        except Exception as e:
            raise ProcessActionError(f"Failed to kill process: {e}", "general")
    
    def get_audit_log(self) -> list:
        return self.audit_log


# Global instance
process_action_manager = ProcessActionManager()
