"""Folder-size and file-type analysis.

The service traverses one or more roots without following links or reparse
points. It stores aggregates and bounded error/type summaries rather than a
list of every discovered file.
"""

import os
import stat as stat_module
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

OTHER_TYPE_KEY = "__other__"
NO_EXTENSION_KEY = ""


def _is_reparse_point(stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0) or 0
    reparse_flag = getattr(
        stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
    )
    return bool(attributes & reparse_flag)


def _is_link_or_reparse(stat_result) -> bool:
    return stat_module.S_ISLNK(stat_result.st_mode) or _is_reparse_point(
        stat_result
    )


def _normalise_roots(roots: Iterable[str]) -> List[str]:
    unique = []
    seen = set()
    for root in roots or []:
        text = str(root or "").strip()
        if not text:
            continue
        path = os.path.abspath(os.path.expanduser(text))
        key = os.path.normcase(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)

    kept = []
    for path in sorted(unique, key=lambda item: (len(item), item)):
        key = os.path.normcase(path)
        if any(_is_within(key, os.path.normcase(parent)) for parent in kept):
            continue
        kept.append(path)
    return kept


def _is_within(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except (TypeError, ValueError):
        return False


def _directory_key(path: str, stat_result) -> Tuple:
    inode = getattr(stat_result, "st_ino", 0)
    device = getattr(stat_result, "st_dev", 0)
    if inode:
        return ("inode", device, inode)
    return ("path", os.path.normcase(os.path.abspath(path)))


def _hardlink_key(stat_result) -> Optional[Tuple[int, int]]:
    links = getattr(stat_result, "st_nlink", 1) or 1
    inode = getattr(stat_result, "st_ino", 0)
    if links > 1 and inode:
        return (
            getattr(stat_result, "st_dev", 0),
            inode,
        )
    return None


def _error(path: str, exc: BaseException, kind: str) -> Dict[str, str]:
    return {"path": path, "error": str(exc), "kind": kind}


class StorageAnalysis:
    """Analyze folder sizes and file types with bounded memory use."""

    def __init__(self, max_file_types: int = 200, max_errors: int = 100):
        self.max_file_types = max(1, int(max_file_types))
        self.max_errors = max(0, int(max_errors))

    def analyze(
        self,
        roots: Iterable[str],
        cancel_event=None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        started = time.monotonic()
        root_paths = _normalise_roots(roots)
        state: Dict[str, Any] = {
            "roots": root_paths,
            "folders": [],
            "root_summaries": [],
            "file_types": {},
            "errors": [],
            "skipped_count": 0,
            "excluded_links": 0,
            "duplicate_objects": 0,
            "files": 0,
            "directories": 0,
            "bytes": 0,
            "visited_dirs": set(),
            "hardlinks": set(),
            "cancelled": False,
            "successful_roots": 0,
            "failed_roots": 0,
            "started": started,
            "error": "",
        }

        if not root_paths:
            state["error"] = "No scan roots provided"
            return self._build_result(state, "failed", progress_callback)

        self._emit_progress(state, root_paths[0], progress_callback)
        for root in root_paths:
            if self._cancelled(cancel_event, state):
                break
            self._analyze_root(
                root, state, cancel_event, progress_callback
            )
            if state["cancelled"]:
                break

        if state["cancelled"]:
            status = "cancelled"
        elif state["successful_roots"] == 0:
            status = "failed"
            if not state["error"]:
                state["error"] = "No usable scan roots"
        elif state["failed_roots"] or state["skipped_count"]:
            status = "partial"
        else:
            status = "complete"

        result = self._build_result(state, status, progress_callback)
        self._emit_progress(state, "", progress_callback)
        return result

    def _analyze_root(
        self, root, state, cancel_event, progress_callback
    ):
        summary = {
            "path": root,
            "size": 0,
            "file_count": 0,
            "directory_count": 0,
            "direct_size": 0,
            "direct_file_count": 0,
            "skipped_count": 0,
            "excluded_links": 0,
            "status": "complete",
        }
        state["root_summaries"].append(summary)

        try:
            root_stat = os.lstat(root)
        except FileNotFoundError as exc:
            self._record_error(
                state, summary, None, root, exc, "missing"
            )
            summary["status"] = "failed"
            state["failed_roots"] += 1
            return
        except PermissionError as exc:
            self._record_error(
                state, summary, None, root, exc, "permission"
            )
            summary["status"] = "failed"
            state["failed_roots"] += 1
            return
        except OSError as exc:
            self._record_error(state, summary, None, root, exc, "os")
            summary["status"] = "failed"
            state["failed_roots"] += 1
            return

        if _is_link_or_reparse(root_stat):
            state["excluded_links"] += 1
            summary["excluded_links"] += 1
            self._record_error(
                state,
                summary,
                None,
                root,
                "Approved root is a symbolic link or reparse point",
                "link",
            )
            summary["status"] = "failed"
            state["failed_roots"] += 1
            return

        if not stat_module.S_ISDIR(root_stat.st_mode):
            self._record_error(
                state,
                summary,
                None,
                root,
                "Path is not a directory",
                "not_directory",
            )
            summary["status"] = "failed"
            state["failed_roots"] += 1
            return

        root_key = _directory_key(root, root_stat)
        if root_key in state["visited_dirs"]:
            summary["status"] = "complete"
            state["successful_roots"] += 1
            return
        state["visited_dirs"].add(root_key)
        state["directories"] += 1
        summary["directory_count"] = 1
        self._emit_progress(state, root, progress_callback)

        try:
            iterator = os.scandir(root)
        except PermissionError as exc:
            self._record_error(
                state, summary, None, root, exc, "permission"
            )
            summary["status"] = "failed"
            state["failed_roots"] += 1
            return
        except OSError as exc:
            self._record_error(state, summary, None, root, exc, "os")
            summary["status"] = "failed"
            state["failed_roots"] += 1
            return

        try:
            with iterator:
                for dir_entry in iterator:
                    if self._cancelled(cancel_event, state):
                        break
                    try:
                        stat_result = os.lstat(dir_entry.path)
                    except FileNotFoundError as exc:
                        self._record_error(
                            state,
                            summary,
                            None,
                            dir_entry.path,
                            exc,
                            "missing",
                        )
                        continue
                    except PermissionError as exc:
                        self._record_error(
                            state,
                            summary,
                            None,
                            dir_entry.path,
                            exc,
                            "permission",
                        )
                        continue
                    except OSError as exc:
                        self._record_error(
                            state,
                            summary,
                            None,
                            dir_entry.path,
                            exc,
                            "os",
                        )
                        continue

                    if _is_link_or_reparse(stat_result):
                        state["excluded_links"] += 1
                        summary["excluded_links"] += 1
                        continue

                    if stat_module.S_ISDIR(stat_result.st_mode):
                        folder_key = _directory_key(
                            dir_entry.path, stat_result
                        )
                        if folder_key in state["visited_dirs"]:
                            state["duplicate_objects"] += 1
                            continue
                        state["visited_dirs"].add(folder_key)
                        state["directories"] += 1
                        summary["directory_count"] += 1
                        folder = {
                            "name": dir_entry.name,
                            "path": dir_entry.path,
                            "root": root,
                            "size": 0,
                            "file_count": 0,
                            "directory_count": 1,
                            "skipped_count": 0,
                            "excluded_links": 0,
                            "status": "complete",
                        }
                        state["folders"].append(folder)
                        self._walk_tree(
                            dir_entry.path,
                            folder,
                            summary,
                            state,
                            cancel_event,
                            progress_callback,
                        )
                        if state["cancelled"]:
                            break
                    elif stat_module.S_ISREG(stat_result.st_mode):
                        self._add_file(
                            dir_entry.path,
                            stat_result,
                            None,
                            summary,
                            state,
                            progress_callback,
                        )
                        if self._cancelled(cancel_event, state):
                            break
        except OSError as exc:
            self._record_error(
                state, summary, None, root, exc, "os"
            )

        if state["cancelled"]:
            summary["status"] = "cancelled"
        elif summary["skipped_count"]:
            summary["status"] = "partial"
        else:
            summary["status"] = "complete"

        if summary["status"] != "failed":
            state["successful_roots"] += 1

    def _walk_tree(
        self,
        start_path,
        folder,
        root_summary,
        state,
        cancel_event,
        progress_callback,
    ):
        stack = [start_path]
        while stack:
            if self._cancelled(cancel_event, state):
                folder["status"] = "partial"
                return
            dirpath = stack.pop()
            try:
                iterator = os.scandir(dirpath)
            except FileNotFoundError as exc:
                self._record_error(
                    state, root_summary, folder, dirpath, exc, "missing"
                )
                continue
            except PermissionError as exc:
                self._record_error(
                    state,
                    root_summary,
                    folder,
                    dirpath,
                    exc,
                    "permission",
                )
                continue
            except OSError as exc:
                self._record_error(
                    state, root_summary, folder, dirpath, exc, "os"
                )
                continue

            try:
                with iterator:
                    for dir_entry in iterator:
                        if self._cancelled(cancel_event, state):
                            folder["status"] = "partial"
                            return
                        try:
                            stat_result = os.lstat(dir_entry.path)
                        except FileNotFoundError as exc:
                            self._record_error(
                                state,
                                root_summary,
                                folder,
                                dir_entry.path,
                                exc,
                                "missing",
                            )
                            continue
                        except PermissionError as exc:
                            self._record_error(
                                state,
                                root_summary,
                                folder,
                                dir_entry.path,
                                exc,
                                "permission",
                            )
                            continue
                        except OSError as exc:
                            self._record_error(
                                state,
                                root_summary,
                                folder,
                                dir_entry.path,
                                exc,
                                "os",
                            )
                            continue

                        if _is_link_or_reparse(stat_result):
                            state["excluded_links"] += 1
                            folder["excluded_links"] += 1
                            root_summary["excluded_links"] += 1
                            continue

                        if stat_module.S_ISDIR(stat_result.st_mode):
                            child_key = _directory_key(
                                dir_entry.path, stat_result
                            )
                            if child_key in state["visited_dirs"]:
                                state["duplicate_objects"] += 1
                                continue
                            state["visited_dirs"].add(child_key)
                            state["directories"] += 1
                            folder["directory_count"] += 1
                            root_summary["directory_count"] += 1
                            stack.append(dir_entry.path)
                        elif stat_module.S_ISREG(stat_result.st_mode):
                            self._add_file(
                                dir_entry.path,
                                stat_result,
                                folder,
                                root_summary,
                                state,
                                progress_callback,
                            )
                            if self._cancelled(
                                cancel_event, state
                            ):
                                folder["status"] = "partial"
                                return
            except OSError as exc:
                self._record_error(
                    state, root_summary, folder, dirpath, exc, "os"
                )
            self._emit_progress(state, dirpath, progress_callback)

        if folder["skipped_count"]:
            folder["status"] = "partial"

    def _add_file(
        self,
        path,
        stat_result,
        folder,
        root_summary,
        state,
        progress_callback,
    ):
        hard_key = _hardlink_key(stat_result)
        if hard_key is not None:
            if hard_key in state["hardlinks"]:
                state["duplicate_objects"] += 1
                return
            state["hardlinks"].add(hard_key)

        size = int(getattr(stat_result, "st_size", 0) or 0)
        state["files"] += 1
        state["bytes"] += size
        root_summary["file_count"] += 1
        root_summary["size"] += size
        if folder is None:
            root_summary["direct_file_count"] += 1
            root_summary["direct_size"] += size
        else:
            folder["file_count"] += 1
            folder["size"] += size

        extension = os.path.splitext(os.path.basename(path))[1].lower()
        type_key = (
            extension
            if extension and extension != "."
            else NO_EXTENSION_KEY
        )
        if (
            type_key not in state["file_types"]
            and len(state["file_types"]) >= self.max_file_types
        ):
            type_key = OTHER_TYPE_KEY
        bucket = state["file_types"].setdefault(
            type_key, {"count": 0, "size": 0}
        )
        bucket["count"] += 1
        bucket["size"] += size

        self._emit_progress(state, path, progress_callback)

    def _record_error(
        self,
        state,
        root_summary,
        folder,
        path,
        exc,
        kind,
    ):
        state["skipped_count"] += 1
        root_summary["skipped_count"] += 1
        if folder is not None:
            folder["skipped_count"] += 1
            folder["status"] = "partial"
        if len(state["errors"]) < self.max_errors:
            state["errors"].append(_error(str(path), exc, kind))

    @staticmethod
    def _cancelled(cancel_event, state):
        if cancel_event is not None and cancel_event.is_set():
            state["cancelled"] = True
            return True
        return False

    def _emit_progress(self, state, path, progress_callback):
        if progress_callback is None:
            return
        progress_callback(
            {
                "files_scanned": state["files"],
                "directories_scanned": state["directories"],
                "bytes_scanned": state["bytes"],
                "current_path": str(path or ""),
                "elapsed_seconds": time.monotonic()
                - state["started"],
            }
        )

    def _build_file_types(self, state):
        total = state["bytes"]
        rows = []
        for key, bucket in state["file_types"].items():
            if key == NO_EXTENSION_KEY:
                label = "No extension"
            elif key == OTHER_TYPE_KEY:
                label = "Other"
            else:
                label = key
            size = int(bucket["size"])
            percentage = (
                (size / total * 100.0) if total else 0.0
            )
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "count": int(bucket["count"]),
                    "size": size,
                    "percentage": percentage,
                }
            )
        rows.sort(key=lambda item: (-item["size"], item["label"].casefold()))
        return rows

    def _build_result(self, state, status, progress_callback):
        folders = sorted(
            state["folders"],
            key=lambda item: (-item["size"], item["name"].casefold()),
        )
        return {
            "roots": list(state["roots"]),
            "status": status,
            "complete": status == "complete",
            "partial": status == "partial",
            "cancelled": status == "cancelled",
            "failed": status == "failed",
            "total_size": int(state["bytes"]),
            "file_count": int(state["files"]),
            "directory_count": int(state["directories"]),
            "skipped_count": int(state["skipped_count"]),
            "excluded_links": int(state["excluded_links"]),
            "duplicate_objects": int(state["duplicate_objects"]),
            "folders": folders,
            "file_types": self._build_file_types(state),
            "root_summaries": list(state["root_summaries"]),
            "errors": list(state["errors"]),
            "error": str(state.get("error") or ""),
            "elapsed_seconds": time.monotonic()
            - state["started"],
        }
