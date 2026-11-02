"""Read-only directory listing for the Storage Explorer.

Lists one directory at a time. It never recurses, follows links, opens files,
or modifies filesystem entries.
"""

import os
import stat as stat_module
from datetime import datetime
from typing import Any, Dict, List, Optional

DEFAULT_LIST_LIMIT = 2000

_TYPE_ORDER = {
    "directory": 0,
    "file": 1,
    "link": 2,
    "reparse": 3,
    "other": 4,
}


def _is_reparse_point(stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0) or 0
    reparse_flag = getattr(
        stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
    )
    return bool(attributes & reparse_flag)


def _is_hidden(name: str, stat_result) -> bool:
    if name.startswith("."):
        return True
    hidden_flag = getattr(stat_module, "FILE_ATTRIBUTE_HIDDEN", 0x2)
    attributes = getattr(stat_result, "st_file_attributes", 0) or 0
    return bool(attributes & hidden_flag)


def _format_timestamp(value) -> Optional[str]:
    try:
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def _error(path: str, exc: BaseException, kind: str) -> Dict[str, str]:
    return {"path": path, "error": str(exc), "kind": kind}


def _sort_key(entry: Dict[str, Any]):
    return (
        _TYPE_ORDER.get(entry["type"], _TYPE_ORDER["other"]),
        entry["name"].casefold(),
        entry["name"],
    )


class DirectoryBrowser:
    """List one directory without following links or modifying the filesystem."""

    def __init__(self, limit: int = DEFAULT_LIST_LIMIT):
        self.limit = max(1, int(limit))

    def list_directory(
        self,
        path: str,
        limit: Optional[int] = None,
        cancel_event=None,
    ) -> Dict[str, Any]:
        target = os.path.abspath(os.path.expanduser(str(path)))
        effective_limit = (
            self.limit if limit is None else max(1, int(limit))
        )
        result: Dict[str, Any] = {
            "path": target,
            "entries": [],
            "errors": [],
            "truncated": False,
            "limit": effective_limit,
            "cancelled": False,
            "error": None,
        }

        if cancel_event is not None and cancel_event.is_set():
            result["cancelled"] = True
            return result

        try:
            iterator = os.scandir(target)
        except FileNotFoundError as exc:
            result["error"] = _error(target, exc, "missing")
            return result
        except PermissionError as exc:
            result["error"] = _error(target, exc, "permission")
            return result
        except NotADirectoryError as exc:
            result["error"] = _error(target, exc, "not_directory")
            return result
        except OSError as exc:
            result["error"] = _error(target, exc, "os")
            return result

        try:
            with iterator:
                for dir_entry in iterator:
                    if (
                        cancel_event is not None
                        and cancel_event.is_set()
                    ):
                        result["cancelled"] = True
                        break
                    if len(result["entries"]) >= effective_limit:
                        result["truncated"] = True
                        break

                    full_path = dir_entry.path
                    try:
                        stat_result = os.lstat(full_path)
                    except FileNotFoundError as exc:
                        result["errors"].append(
                            _error(full_path, exc, "missing")
                        )
                        continue
                    except PermissionError as exc:
                        result["errors"].append(
                            _error(full_path, exc, "permission")
                        )
                        continue
                    except OSError as exc:
                        result["errors"].append(
                            _error(full_path, exc, "os")
                        )
                        continue

                    is_link = stat_module.S_ISLNK(stat_result.st_mode)
                    is_reparse = _is_reparse_point(stat_result)
                    if is_link:
                        entry_type = "link"
                    elif is_reparse:
                        entry_type = "reparse"
                    elif stat_module.S_ISDIR(stat_result.st_mode):
                        entry_type = "directory"
                    elif stat_module.S_ISREG(stat_result.st_mode):
                        entry_type = "file"
                    else:
                        entry_type = "other"

                    is_file = entry_type == "file"
                    is_dir = entry_type == "directory"
                    result["entries"].append(
                        {
                            "name": dir_entry.name,
                            "path": full_path,
                            "type": entry_type,
                            "size": (
                                stat_result.st_size if is_file else None
                            ),
                            "modified": _format_timestamp(
                                getattr(stat_result, "st_mtime", None)
                            ),
                            "is_dir": is_dir,
                            "is_file": is_file,
                            "is_link": is_link,
                            "is_reparse": is_reparse,
                            "is_hidden": _is_hidden(
                                dir_entry.name, stat_result
                            ),
                        }
                    )
        except OSError as exc:
            result["error"] = _error(target, exc, "os")

        result["entries"].sort(key=_sort_key)
        return result
