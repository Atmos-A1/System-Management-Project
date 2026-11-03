"""Cleanup manager for safe file removal.

Cleanup is Recycle Bin/trash-only. Permanent deletion is intentionally
unsupported. Every target must be a regular, non-link file under an explicitly
approved scan root and outside protected system/application locations.
"""

import json
import os
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Dict, List, Optional

from .cleanup_policy import Identity, inspect_path, inspect_paths, is_valid_identity

try:
    from send2trash import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False
    send2trash = None


class CleanupManager:
    def __init__(self, audit_log=None, history_recorder=None):
        self.audit_log = audit_log if audit_log is not None else []
        self._history_recorder = history_recorder

    def _log_action(
        self, action: str, paths: List[str], result: str, details: str = ""
    ):
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

    def _record_history(self, payload: Dict[str, Any]) -> None:
        try:
            detail = json.dumps(payload, default=str)
            if self._history_recorder is not None:
                self._history_recorder("storage_cleanup", detail)
            else:
                from .history import record_event

                record_event("storage_cleanup", detail)
        except Exception:
            # History is best-effort and must never hide cleanup outcomes.
            pass

    def preflight_cleanup(
        self, file_paths: List[str], allowed_roots: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Advisory preflight. The move operation revalidates each file.

        Allowed decisions carry the identity captured from the same ``lstat``
        used for validation. A file whose identity cannot be established is
        rejected here so the review dialog and execution agree.
        """
        decisions = inspect_paths(
            [str(path) for path in file_paths], allowed_roots or []
        )
        decision_dicts: List[Dict[str, Any]] = []
        identities: Dict[str, Identity] = {}
        for decision in decisions:
            allowed = decision.allowed
            reason = decision.reason
            if allowed and decision.identity is None:
                allowed = False
                reason = "File identity cannot be verified"
            item: Dict[str, Any] = {
                "path": decision.path,
                "allowed": allowed,
                "reason": reason,
            }
            if allowed:
                item["identity"] = decision.identity
                identities[decision.path] = decision.identity
            decision_dicts.append(item)
        return {
            "decisions": decision_dicts,
            "allowed": [
                item["path"] for item in decision_dicts if item["allowed"]
            ],
            "rejected": [
                item for item in decision_dicts if not item["allowed"]
            ],
            "identities": identities,
        }

    def move_to_recycle_bin(
        self,
        file_paths: List[str],
        allowed_roots: Optional[List[str]] = None,
        expected_identities: Optional[Mapping[str, Identity]] = None,
    ) -> Dict[str, Any]:
        """Move eligible files to the Recycle Bin.

        ``allowed_roots`` is required in practice; omitting it makes every path
        fail closed. The preflight is advisory and each file is inspected again
        immediately before it is passed to send2trash.

        ``expected_identities`` carries the identities captured during the
        original review preview. When omitted, identities from this execution
        preflight are used; that fallback does not protect the interval
        between preview and execution.
        """
        requested = [str(path) for path in file_paths]
        preflight = self.preflight_cleanup(requested, allowed_roots)
        roots = [str(root) for root in (allowed_roots or []) if root]
        identity_mapping_error = ""
        reviewed: Optional[Dict[str, Identity]]
        if expected_identities is None:
            reviewed = None
        elif isinstance(expected_identities, Mapping):
            try:
                reviewed = dict(expected_identities)
            except Exception:
                reviewed = {}
                identity_mapping_error = (
                    "Cleanup review identity mapping is invalid"
                )
        else:
            reviewed = {}
            identity_mapping_error = (
                "Cleanup review identity mapping is invalid"
            )

        outcomes: List[Dict[str, str]] = []
        moved_paths: List[str] = []

        if not HAS_SEND2TRASH:
            reason = (
                "send2trash is unavailable; files cannot be moved to the "
                "Recycle Bin"
            )
            outcomes = [
                {"path": path, "status": "failed", "reason": reason}
                for path in requested
            ]
            result = self._result(outcomes, moved_paths, reason=reason)
            self._finalize("recycle_bin", requested, result)
            return result

        for decision in preflight["decisions"]:
            path = decision["path"]
            if not decision["allowed"]:
                outcomes.append(
                    {
                        "path": path,
                        "status": "rejected",
                        "reason": decision["reason"],
                    }
                )
                continue

            # Preflight is advisory: revalidate immediately before trash.
            fresh = inspect_path(path, roots)
            if not fresh.allowed:
                outcomes.append(
                    {
                        "path": path,
                        "status": "rejected",
                        "reason": fresh.reason,
                    }
                )
                continue

            expected = (
                reviewed.get(path)
                if reviewed is not None
                else decision.get("identity")
            )
            if identity_mapping_error:
                reason = identity_mapping_error
            elif expected is None:
                reason = "File identity cannot be verified"
            elif not is_valid_identity(expected):
                reason = "Cleanup review identity is invalid"
            elif not is_valid_identity(fresh.identity):
                reason = "File identity cannot be verified"
            elif fresh.identity != expected:
                reason = "File changed since cleanup review"
            else:
                reason = ""
            if reason:
                outcomes.append(
                    {
                        "path": path,
                        "status": "rejected",
                        "reason": reason,
                    }
                )
                continue

            try:
                send2trash(path)
                moved_paths.append(path)
                outcomes.append(
                    {"path": path, "status": "moved", "reason": ""}
                )
            except Exception as exc:
                outcomes.append(
                    {
                        "path": path,
                        "status": "failed",
                        "reason": str(exc),
                    }
                )

        result = self._result(outcomes, moved_paths)
        self._finalize("recycle_bin", requested, result)
        return result

    def permanent_delete(self, file_paths: List[str]) -> Dict[str, Any]:
        """Permanent deletion is not available in the cleanup workflow."""
        raise PermissionError(
            "Permanent deletion is not supported. Use the Recycle Bin "
            "workflow instead."
        )

    def _result(
        self,
        outcomes: List[Dict[str, str]],
        moved_paths: List[str],
        reason: str = "",
    ) -> Dict[str, Any]:
        failed = [item for item in outcomes if item["status"] != "moved"]
        result = {
            "success": len(moved_paths) > 0,
            "moved": len(moved_paths),
            "failed": len(failed),
            "rejected": sum(
                1 for item in outcomes if item["status"] == "rejected"
            ),
            "details": {
                "success": moved_paths,
                "failed": [
                    (item["path"], item["reason"]) for item in failed
                ],
            },
            "outcomes": outcomes,
        }
        if reason:
            result["error"] = reason
        return result

    def _finalize(
        self, action: str, requested: List[str], result: Dict[str, Any]
    ) -> None:
        if result["moved"] == 0:
            status = "failed"
        elif result["failed"]:
            status = "partial"
        else:
            status = "success"
        self._log_action(
            action,
            requested,
            status,
            f"Moved: {result['moved']}, Failed: {result['failed']}",
        )
        self._record_history(
            {
                "operation": action,
                "requested": len(requested),
                "moved": result["moved"],
                "failed": result["failed"],
                "outcomes": result["outcomes"],
            }
        )

    def get_audit_log(self) -> list:
        return self.audit_log


cleanup_manager = CleanupManager()
