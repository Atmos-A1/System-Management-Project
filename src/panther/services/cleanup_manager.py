"""Cleanup manager for safe file deletion.

Defaults to moving files to Recycle Bin. Permanent deletion requires
explicit confirmation.
"""

import os
from typing import List, Dict, Any
from datetime import datetime

try:
    from send2trash import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False


_PROTECTED_ENV_VARS = ("WINDIR", "SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData")


def protected_roots() -> List[str]:
    """Locations cleanup must never touch (PRD 5.3: protected locations).

    Evaluated at call time so the environment is always current.
    """
    roots = []
    for var in _PROTECTED_ENV_VARS:
        value = os.environ.get(var)
        if value:
            roots.append(os.path.normcase(os.path.realpath(value)))
    return roots


def is_protected_path(path: str) -> bool:
    """True if *path* is, or is inside, a protected location.

    The real path is used so ``..`` segments and symlinks pointing into a
    protected folder cannot be used to bypass the check.
    """
    real = os.path.normcase(os.path.realpath(path))
    for root in protected_roots():
        if real == root or real.startswith(root.rstrip(os.sep) + os.sep):
            return True
    return False


class CleanupManager:
    def __init__(self, audit_log=None):
        self.audit_log = audit_log or []
    
    def _log_action(self, action: str, paths: List[str], result: str, details: str = ""):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "paths": paths,
            "count": len(paths),
            "result": result,
            "details": details,
        }
        self.audit_log.append(entry)
        return entry
    
    def move_to_recycle_bin(self, file_paths: List[str]) -> Dict[str, Any]:
        """Move files to Recycle Bin (reversible where supported)."""
        if not HAS_SEND2TRASH:
            return {
                "success": False,
                "error": "send2trash not available. Install it with: pip install Send2Trash"
            }
        
        results = {"success": [], "failed": []}
        for path in file_paths:
            try:
                if is_protected_path(path):
                    results["failed"].append((path, "Protected location - not eligible for cleanup"))
                    continue
                if not os.path.exists(path):
                    results["failed"].append((path, "File does not exist"))
                    continue
                send2trash(path)
                results["success"].append(path)
            except Exception as e:
                results["failed"].append((path, str(e)))
        
        self._log_action("recycle_bin", file_paths, 
                        "partial" if results["failed"] else "success",
                        f"Success: {len(results['success'])}, Failed: {len(results['failed'])}")
        
        return {
            "success": len(results["success"]) > 0,
            "moved": len(results["success"]),
            "failed": len(results["failed"]),
            "details": results
        }
    
    def permanent_delete(self, file_paths: List[str]) -> Dict[str, Any]:
        """Permanently delete files. Use with extreme caution."""
        results = {"success": [], "failed": []}
        for path in file_paths:
            try:
                if is_protected_path(path):
                    results["failed"].append((path, "Protected location - not eligible for cleanup"))
                    continue
                if not os.path.exists(path):
                    results["failed"].append((path, "File does not exist"))
                    continue
                if os.path.isfile(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    os.rmdir(path)
                results["success"].append(path)
            except Exception as e:
                results["failed"].append((path, str(e)))
        
        self._log_action("permanent_delete", file_paths,
                        "partial" if results["failed"] else "success",
                        f"Success: {len(results['success'])}, Failed: {len(results['failed'])}")
        
        return {
            "success": len(results["success"]) > 0,
            "deleted": len(results["success"]),
            "failed": len(results["failed"]),
            "details": results
        }
    
    def get_audit_log(self) -> list:
        return self.audit_log


cleanup_manager = CleanupManager()
