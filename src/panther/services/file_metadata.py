"""Safe, read-only filesystem metadata inspection.

Only ``lstat`` is used so symbolic links and reparse points are never followed.
The service returns plain data and never opens, executes, or modifies entries.
"""

import os
import stat as stat_module
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


_CLASSIFICATIONS = {
    ".pdf": "PDF document",
    ".png": "PNG image",
    ".jpg": "JPEG image",
    ".jpeg": "JPEG image",
    ".gif": "GIF image",
    ".txt": "Text file",
    ".md": "Markdown file",
    ".py": "Python source",
    ".zip": "ZIP archive",
    ".gz": "GZIP archive",
    ".tar": "Tar archive",
    ".mp3": "MP3 audio",
    ".wav": "WAV audio",
    ".doc": "Word document",
    ".docx": "Word document",
    ".xls": "Spreadsheet",
    ".xlsx": "Spreadsheet",
    ".ppt": "Presentation",
    ".pptx": "Presentation",
    ".exe": "Windows executable",
    ".dll": "Windows library",
    ".elf": "ELF binary",
    ".json": "JSON file",
    ".csv": "CSV file",
}

_WINDOWS_ATTRIBUTES: Tuple[Tuple[int, str], ...] = (
    (0x1, "Read-only"),
    (0x2, "Hidden"),
    (0x4, "System"),
    (0x10, "Directory"),
    (0x20, "Archive"),
    (0x400, "Reparse point"),
)


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


def _creation_timestamp(stat_result) -> Optional[str]:
    birth = getattr(stat_result, "st_birthtime", None)
    if birth not in (None, 0):
        return _format_timestamp(birth)
    if os.name == "nt":
        return _format_timestamp(getattr(stat_result, "st_ctime", None))
    return None


def _extension(name: str) -> str:
    extension = os.path.splitext(name)[1].lower()
    return "" if extension == "." else extension


def _classification(entry_type: str, extension: str) -> str:
    if entry_type == "directory":
        return "Folder"
    if entry_type == "link":
        return "Symbolic link"
    if entry_type == "reparse":
        return "Reparse point"
    if entry_type == "other":
        return "Other"
    return _CLASSIFICATIONS.get(extension, "File")


def _is_read_only(stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0) or 0
    read_only_flag = getattr(stat_module, "FILE_ATTRIBUTE_READONLY", 0x1)
    if os.name == "nt" and attributes & read_only_flag:
        return True
    write_bits = stat_module.S_IWUSR | stat_module.S_IWGRP | stat_module.S_IWOTH
    return not bool(getattr(stat_result, "st_mode", 0) & write_bits)


def _attributes(stat_result) -> Tuple[List[str], bool]:
    if os.name != "nt" or not hasattr(stat_result, "st_file_attributes"):
        return [], False
    attributes = getattr(stat_result, "st_file_attributes", 0) or 0
    names = [
        label for flag, label in _WINDOWS_ATTRIBUTES if attributes & flag
    ]
    return names, True


def _entry_type(stat_result) -> str:
    if stat_module.S_ISLNK(stat_result.st_mode):
        return "link"
    if _is_reparse_point(stat_result):
        return "reparse"
    if stat_module.S_ISDIR(stat_result.st_mode):
        return "directory"
    if stat_module.S_ISREG(stat_result.st_mode):
        return "file"
    return "other"


def _empty_result(path: str, name: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "path": path,
        "name": name,
        "entry_type": None,
        "extension": _extension(name),
        "size": None,
        "created": None,
        "created_available": False,
        "modified": None,
        "accessed": None,
        "is_hidden": False,
        "is_read_only": False,
        "is_link": False,
        "is_reparse": False,
        "is_file": False,
        "is_dir": False,
        "classification": "Unknown",
        "attributes": [],
        "attributes_supported": False,
        "error": "",
        "error_kind": None,
    }


class FileMetadataInspector:
    """Inspect metadata for one entry without following links."""

    def inspect(self, path: str) -> Dict[str, Any]:
        target = os.path.abspath(os.path.expanduser(str(path)))
        name = os.path.basename(target)
        result = _empty_result(target, name)

        try:
            stat_result = os.lstat(target)
        except FileNotFoundError as exc:
            result["error_kind"] = "missing"
            result["error"] = str(exc) or "Entry disappeared"
            return result
        except PermissionError as exc:
            result["error_kind"] = "permission"
            result["error"] = str(exc) or "Permission denied"
            return result
        except OSError as exc:
            result["error_kind"] = "os"
            result["error"] = str(exc) or "Cannot inspect entry"
            return result

        entry_type = _entry_type(stat_result)
        is_link = entry_type == "link"
        is_reparse = entry_type == "reparse"
        created = _creation_timestamp(stat_result)
        attributes, attributes_supported = _attributes(stat_result)

        result.update(
            {
                "entry_type": entry_type,
                "size": (
                    int(stat_result.st_size)
                    if entry_type == "file"
                    else None
                ),
                "created": created,
                "created_available": created is not None,
                "modified": _format_timestamp(
                    getattr(stat_result, "st_mtime", None)
                ),
                "accessed": _format_timestamp(
                    getattr(stat_result, "st_atime", None)
                ),
                "is_hidden": _is_hidden(name, stat_result),
                "is_read_only": _is_read_only(stat_result),
                "is_link": is_link,
                "is_reparse": is_reparse,
                "is_file": entry_type == "file",
                "is_dir": entry_type == "directory",
                "classification": _classification(
                    entry_type, _extension(name)
                ),
                "attributes": attributes,
                "attributes_supported": attributes_supported,
            }
        )

        if is_link:
            result["error_kind"] = "link"
            result["error"] = "Symbolic links are not inspected."
        elif is_reparse:
            result["error_kind"] = "reparse"
            result["error"] = "Reparse points are not inspected."
        elif entry_type == "other":
            result["error_kind"] = "unsupported"
            result["error"] = "Unsupported entry type."
        else:
            result["ok"] = True

        return result
