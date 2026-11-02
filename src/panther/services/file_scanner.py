"""File scanner service.

Scans directories to collect file metadata for analysis.

The scanner supports a bounded traversal depth, cooperative cancellation,
progress reporting and explicit filesystem error reporting. It never follows
symbolic links or Windows reparse points.
"""

import os
import stat as stat_module
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

FileRecord = Dict[str, Any]
ScanError = Dict[str, str]
ProgressCallback = Any
ErrorCallback = Any


def _is_reparse_point(stat_result: Any) -> bool:
    """Return True when a stat result represents a Windows reparse point."""
    attributes = getattr(stat_result, "st_file_attributes", 0) or 0
    reparse_flag = getattr(
        stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
    )
    return bool(attributes & reparse_flag)


def _is_link_or_reparse(stat_result: Any) -> bool:
    return stat_module.S_ISLNK(stat_result.st_mode) or _is_reparse_point(
        stat_result
    )


def _is_hidden(stat_result: Any, name: str) -> bool:
    if name.startswith("."):
        return True
    hidden_flag = getattr(stat_module, "FILE_ATTRIBUTE_HIDDEN", 0x2)
    attributes = getattr(stat_result, "st_file_attributes", 0) or 0
    return bool(attributes & hidden_flag)


def _format_timestamp(value: float) -> Optional[str]:
    try:
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return None


class FileScanner:
    def __init__(self):
        self.scanning = False
        self.cancelled = False
        self.last_errors: List[ScanError] = []
        self.last_progress: Dict[str, Any] = {}

        self._cancel_event: Optional[threading.Event] = None
        self._progress_callback = None
        self._error_callback = None
        self._started_at = 0.0
        self._files_scanned = 0
        self._directories_scanned = 0
        self._bytes_scanned = 0

    def scan_directory(
        self,
        root_path: str,
        max_depth: Optional[int] = 10,
        include_hidden: bool = False,
        cancel_event: Optional[threading.Event] = None,
        progress_callback=None,
        error_callback=None,
    ) -> List[FileRecord]:
        """Scan a directory and return file metadata records.

        ``max_depth`` is zero-based: ``0`` scans only files directly inside
        ``root_path``; ``1`` also scans immediate child directories. ``None``
        removes the limit. Cancellation is cooperative via ``cancel_event`` or
        :meth:`cancel`. Filesystem errors are collected in ``last_errors`` and
        passed to ``error_callback`` when supplied.
        """
        if max_depth is not None and max_depth < 0:
            raise ValueError("max_depth must be >= 0 or None")

        self.scanning = True
        self.cancelled = False
        self.last_errors = []
        self.last_progress = {}
        self._files_scanned = 0
        self._directories_scanned = 0
        self._bytes_scanned = 0
        self._started_at = time.monotonic()
        self._progress_callback = progress_callback
        self._error_callback = error_callback
        self._cancel_event = (
            cancel_event if cancel_event is not None else threading.Event()
        )

        files: List[FileRecord] = []

        try:
            root = Path(root_path)
            if not root.exists():
                self._record_error(root, "Path does not exist", "missing")
                return files
            if not root.is_dir():
                self._record_error(
                    root, "Path is not a directory", "not_directory"
                )
                return files

            try:
                root_stat = os.lstat(str(root))
            except OSError as exc:
                self._record_error(root, exc)
                return files

            if _is_link_or_reparse(root_stat):
                self._record_error(
                    root,
                    "Path is a symbolic link or reparse point",
                    "link",
                )
                return files

            if self._check_cancelled():
                return files

            def on_walk_error(exc: OSError) -> None:
                self._record_error(
                    getattr(exc, "filename", str(root)), exc
                )

            for dirpath, dirnames, filenames in os.walk(
                root,
                topdown=True,
                followlinks=False,
                onerror=on_walk_error,
            ):
                if self._check_cancelled():
                    break

                self._directories_scanned += 1
                relative = os.path.relpath(dirpath, root)
                depth = (
                    0
                    if relative == "."
                    else relative.count(os.sep) + 1
                )

                for filename in filenames:
                    if self._check_cancelled():
                        break
                    self._scan_file(
                        os.path.join(dirpath, filename),
                        filename,
                        include_hidden,
                        files,
                    )

                if self._check_cancelled():
                    break

                if max_depth is not None and depth >= max_depth:
                    dirnames[:] = []
                    continue

                dirnames[:] = self._filter_directories(
                    dirpath, dirnames, include_hidden
                )

            return files
        finally:
            self.scanning = False

    def _scan_file(
        self,
        full_path: str,
        filename: str,
        include_hidden: bool,
        files: List[FileRecord],
    ) -> None:
        try:
            stat_result = os.stat(full_path, follow_symlinks=False)
        except OSError as exc:
            self._record_error(full_path, exc)
            return

        if _is_link_or_reparse(stat_result):
            return
        if not include_hidden and _is_hidden(stat_result, filename):
            return

        files.append(
            {
                "name": filename,
                "path": full_path,
                "directory": os.path.dirname(full_path),
                "size": stat_result.st_size,
                "extension": Path(filename).suffix.lower(),
                "created": _format_timestamp(stat_result.st_ctime),
                "modified": _format_timestamp(stat_result.st_mtime),
                "accessed": (
                    _format_timestamp(stat_result.st_atime)
                    if hasattr(stat_result, "st_atime")
                    else None
                ),
                "is_file": True,
            }
        )
        self._files_scanned += 1
        self._bytes_scanned += stat_result.st_size
        self._report_progress(full_path)

    def _filter_directories(
        self, dirpath: str, dirnames: List[str], include_hidden: bool
    ) -> List[str]:
        filtered = []
        for dirname in dirnames:
            full_path = os.path.join(dirpath, dirname)
            try:
                stat_result = os.lstat(full_path)
            except OSError as exc:
                self._record_error(full_path, exc)
                continue

            if _is_link_or_reparse(stat_result):
                continue
            if not include_hidden and _is_hidden(stat_result, dirname):
                continue
            filtered.append(dirname)
        return filtered

    def _check_cancelled(self) -> bool:
        if self.cancelled or (
            self._cancel_event is not None
            and self._cancel_event.is_set()
        ):
            self.cancelled = True
            return True
        return False

    def _report_progress(self, current_path: str) -> None:
        if self._progress_callback is None:
            return
        progress = {
            "files_scanned": self._files_scanned,
            "directories_scanned": self._directories_scanned,
            "bytes_scanned": self._bytes_scanned,
            "current_path": current_path,
            "elapsed_seconds": time.monotonic() - self._started_at,
        }
        self.last_progress = progress
        self._progress_callback(progress)

    def _record_error(self, path, error, kind: Optional[str] = None) -> None:
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
        if self._error_callback is not None:
            self._error_callback(entry)

    def get_largest_files(
        self, files: List[FileRecord], limit: int = 100
    ) -> List[FileRecord]:
        """Get largest files sorted by size."""
        sorted_files = sorted(
            files, key=lambda item: item["size"], reverse=True
        )
        return sorted_files[:limit]

    def cancel(self):
        self.cancelled = True
        if self._cancel_event is not None:
            self._cancel_event.set()


file_scanner = FileScanner()
