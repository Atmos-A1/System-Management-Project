"""Duplicate file detector.

Uses file size as preliminary filter, then cryptographic hash (SHA256)
to identify exact duplicates. Detection is cancellable, reports filesystem
errors and never mutates the input records.
"""

import hashlib
import os
import stat as stat_module
import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from .file_scanner import _is_reparse_point

FileRecord = Dict[str, Any]


def _is_link_or_reparse(path: str) -> bool:
    try:
        stat_result = os.lstat(path)
    except OSError:
        return False
    return stat_module.S_ISLNK(stat_result.st_mode) or _is_reparse_point(
        stat_result
    )


class DuplicateDetector:
    def __init__(self, hash_algorithm: str = "sha256"):
        self.hash_algorithm = hash_algorithm
        self.cancelled = False
        self.last_errors: List[Dict[str, str]] = []

        self._cancel_event: Optional[threading.Event] = None
        self._error_callback = None
        self._started_at = 0.0
        self._files_hashed = 0
        self._bytes_hashed = 0

    def calculate_hash(
        self,
        file_path: str,
        chunk_size: int = 8192,
        cancel_event: Optional[threading.Event] = None,
        error_callback=None,
    ) -> Optional[str]:
        """Calculate the content hash, or return None on error/cancellation.

        Symbolic links and Windows reparse points are never opened or hashed.
        """
        event = cancel_event if cancel_event is not None else self._cancel_event
        if event is not None and event.is_set():
            self.cancelled = True
            return None

        if _is_link_or_reparse(str(file_path)):
            self._record_error(
                file_path,
                "Symbolic links and reparse points are not hashed",
                "link",
                error_callback,
            )
            return None

        hash_obj = hashlib.new(self.hash_algorithm)
        try:
            with open(file_path, "rb") as handle:
                while True:
                    if event is not None and event.is_set():
                        self.cancelled = True
                        return None
                    chunk = handle.read(chunk_size)
                    if not chunk:
                        break
                    hash_obj.update(chunk)
            return hash_obj.hexdigest()
        except (PermissionError, FileNotFoundError, OSError) as exc:
            self._record_error(file_path, exc, None, error_callback)
            return None

    def find_duplicates(
        self,
        files: List[FileRecord],
        cancel_event: Optional[threading.Event] = None,
        progress_callback=None,
        error_callback=None,
    ) -> List[Dict[str, Any]]:
        """Find exact duplicate groups without modifying ``files``.

        Cancellation discards partial results and returns an empty list.
        """
        self.cancelled = False
        self.last_errors = []
        self._files_hashed = 0
        self._bytes_hashed = 0
        self._started_at = time.monotonic()
        self._error_callback = error_callback
        self._cancel_event = (
            cancel_event if cancel_event is not None else threading.Event()
        )

        if self._check_cancelled():
            return []

        size_groups = defaultdict(list)
        for record in files:
            if record.get("size", 0) > 0:
                size_groups[record["size"]].append(record)

        candidate_groups = [
            (size, group)
            for size, group in size_groups.items()
            if len(group) >= 2
        ]
        total_files = sum(len(group) for _, group in candidate_groups)
        total_bytes = sum(
            size * len(group) for size, group in candidate_groups
        )

        duplicates: List[Dict[str, Any]] = []
        for size, file_list in candidate_groups:
            if self._check_cancelled():
                return []

            hash_groups = defaultdict(list)
            for record in file_list:
                if self._check_cancelled():
                    return []

                file_hash = self.calculate_hash(
                    record["path"],
                    cancel_event=self._cancel_event,
                    error_callback=self._error_callback,
                )
                if self.cancelled:
                    return []
                if not file_hash:
                    continue

                copy = dict(record)
                copy["hash"] = file_hash
                hash_groups[file_hash].append(copy)

                self._files_hashed += 1
                self._bytes_hashed += size
                self._report_progress(
                    record["path"],
                    total_files,
                    total_bytes,
                    len(duplicates),
                    progress_callback,
                )

            for file_hash, duplicate_items in hash_groups.items():
                if len(duplicate_items) < 2:
                    continue
                total_size = size * len(duplicate_items)
                potential_savings = size * (
                    len(duplicate_items) - 1
                )
                duplicates.append(
                    {
                        "hash": file_hash,
                        "size": size,
                        "count": len(duplicate_items),
                        "files": duplicate_items,
                        "total_size": total_size,
                        "potential_savings": potential_savings,
                    }
                )

        duplicates.sort(
            key=lambda item: item["potential_savings"], reverse=True
        )
        return duplicates

    def _check_cancelled(self) -> bool:
        if self.cancelled or (
            self._cancel_event is not None
            and self._cancel_event.is_set()
        ):
            self.cancelled = True
            return True
        return False

    def _report_progress(
        self,
        current_path: str,
        total_files: int,
        total_bytes: int,
        groups_found: int,
        progress_callback,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(
            {
                "files_hashed": self._files_hashed,
                "total_files": total_files,
                "bytes_hashed": self._bytes_hashed,
                "total_bytes": total_bytes,
                "groups_found": groups_found,
                "current_path": current_path,
                "elapsed_seconds": time.monotonic() - self._started_at,
            }
        )

    def _record_error(
        self,
        path,
        error,
        kind: Optional[str] = None,
        error_callback=None,
    ) -> None:
        if kind is None:
            if isinstance(error, PermissionError):
                kind = "permission"
            elif isinstance(error, FileNotFoundError):
                kind = "missing"
            else:
                kind = "os"

        entry = {
            "path": str(path),
            "error": str(error),
            "kind": kind,
        }
        self.last_errors.append(entry)
        callback = (
            error_callback
            if error_callback is not None
            else self._error_callback
        )
        if callback is not None:
            callback(entry)

    def cancel(self):
        self.cancelled = True
        if self._cancel_event is not None:
            self._cancel_event.set()


duplicate_detector = DuplicateDetector()
