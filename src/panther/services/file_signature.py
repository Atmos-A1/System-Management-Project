"""Bounded, read-only file-signature inspection.

Only a small fixed prefix of a regular file is read. Files are never executed,
parsed, opened externally, or modified. Symbolic links and reparse points are
rejected before any bytes are read.
"""

import errno
import os
import stat as stat_module
from typing import Any, Dict, Optional, Tuple

MAX_SIGNATURE_BYTES = 64

_FORMAT_LABELS = {
    "PDF": "PDF document",
    "PNG": "PNG image",
    "JPEG": "JPEG image",
    "GIF": "GIF image",
    "ZIP": "ZIP archive",
    "GZIP": "GZIP archive",
    "ELF": "ELF binary",
    "PE": "Windows PE executable",
    "MP3": "MP3 audio",
    "WAV": "WAV audio",
}

_EXPECTED_EXTENSIONS = {
    "PDF": {".pdf"},
    "PNG": {".png"},
    "JPEG": {".jpg", ".jpeg", ".jpe"},
    "GIF": {".gif"},
    "ZIP": {
        ".zip",
        ".jar",
        ".apk",
        ".docx",
        ".xlsx",
        ".pptx",
        ".odt",
        ".ods",
        ".odp",
        ".epub",
    },
    "GZIP": {".gz", ".gzip", ".tgz"},
    "ELF": {".elf", ".so", ".o", ".bin"},
    "PE": {".exe", ".dll", ".sys", ".scr", ".com"},
    "MP3": {".mp3"},
    "WAV": {".wav"},
}

# Small, explicit table. Order matters only if signatures overlap.
_SIGNATURES: Tuple[Dict[str, Any], ...] = (
    {"format": "PDF", "magic": b"%PDF-"},
    {"format": "PNG", "magic": b"\x89PNG\r\n\x1a\n"},
    {"format": "JPEG", "magic": b"\xff\xd8\xff"},
    {"format": "GIF", "magic": b"GIF87a"},
    {"format": "GIF", "magic": b"GIF89a"},
    {"format": "ZIP", "magic": b"PK\x03\x04"},
    {"format": "ZIP", "magic": b"PK\x05\x06"},
    {"format": "ZIP", "magic": b"PK\x07\x08"},
    {"format": "GZIP", "magic": b"\x1f\x8b"},
    {"format": "ELF", "magic": b"\x7fELF"},
    {"format": "PE", "magic": b"MZ"},
    {"format": "MP3", "magic": b"ID3"},
    {"format": "MP3", "magic": b"\xff\xfb"},
    {"format": "MP3", "magic": b"\xff\xf3"},
    {"format": "MP3", "magic": b"\xff\xf2"},
    {
        "format": "WAV",
        "magic": b"RIFF",
        "extra_offset": 8,
        "extra_magic": b"WAVE",
    },
)


def _is_reparse_point(stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0) or 0
    reparse_flag = getattr(
        stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
    )
    return bool(attributes & reparse_flag)


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


def _extension(name: str) -> str:
    extension = os.path.splitext(name)[1].lower()
    return "" if extension == "." else extension


def _match_signature(data: bytes) -> Optional[str]:
    for entry in _SIGNATURES:
        magic = entry["magic"]
        if not data.startswith(magic):
            continue
        extra_magic = entry.get("extra_magic")
        if extra_magic is not None:
            offset = int(entry.get("extra_offset", len(magic)))
            end = offset + len(extra_magic)
            if len(data) < end or data[offset:end] != extra_magic:
                continue
        return entry["format"]
    return None


def _extension_match(
    format_name: Optional[str], extension: str
) -> str:
    if format_name is None:
        return "unknown"
    if not extension:
        return "unavailable"
    expected = _EXPECTED_EXTENSIONS.get(format_name)
    if expected is None:
        return "unknown"
    return "match" if extension in expected else "mismatch"


def _base_result(path: str, name: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "path": path,
        "name": name,
        "status": "unreadable",
        "format": None,
        "format_label": None,
        "entry_type": None,
        "extension": _extension(name),
        "extension_match": "unknown",
        "bytes_read": 0,
        "error": "",
        "error_kind": None,
        "no_follow_supported": bool(getattr(os, "O_NOFOLLOW", 0)),
    }


def _changed(left, right) -> bool:
    left_inode = getattr(left, "st_ino", 0) or 0
    right_inode = getattr(right, "st_ino", 0) or 0
    left_device = getattr(left, "st_dev", 0) or 0
    right_device = getattr(right, "st_dev", 0) or 0
    if left_inode and right_inode:
        if (left_device, left_inode) != (right_device, right_inode):
            return True
    left_size = getattr(left, "st_size", None)
    right_size = getattr(right, "st_size", None)
    if left_size is not None and right_size is not None:
        return int(left_size) != int(right_size)
    return False


class FileSignatureInspector:
    """Identify a limited set of formats from at most 64 leading bytes."""

    def inspect(self, path: str) -> Dict[str, Any]:
        target = os.path.abspath(os.path.expanduser(str(path)))
        name = os.path.basename(target)
        result = _base_result(target, name)

        try:
            before = os.lstat(target)
        except FileNotFoundError as exc:
            result["status"] = "changed"
            result["error_kind"] = "missing"
            result["error"] = str(exc) or "File disappeared"
            return result
        except PermissionError as exc:
            result["status"] = "unreadable"
            result["error_kind"] = "permission"
            result["error"] = str(exc) or "Permission denied"
            return result
        except OSError as exc:
            result["status"] = "unreadable"
            result["error_kind"] = "os"
            result["error"] = str(exc) or "Cannot inspect file"
            return result

        entry_type = _entry_type(before)
        result["entry_type"] = entry_type
        if entry_type == "link":
            result["status"] = "unsupported"
            result["error_kind"] = "link"
            result["error"] = "Symbolic links are not inspected."
            return result
        if entry_type == "reparse":
            result["status"] = "unsupported"
            result["error_kind"] = "reparse"
            result["error"] = "Reparse points are not inspected."
            return result
        if entry_type != "file":
            result["status"] = "unsupported"
            result["error_kind"] = "unsupported"
            result["error"] = "Only regular files have signatures."
            return result

        flags = os.O_RDONLY
        no_follow_flag = getattr(os, "O_NOFOLLOW", 0)
        if no_follow_flag:
            flags |= no_follow_flag
        binary_flag = getattr(os, "O_BINARY", 0)
        if binary_flag:
            flags |= binary_flag
        cloexec_flag = getattr(os, "O_CLOEXEC", 0)
        if cloexec_flag:
            flags |= cloexec_flag

        try:
            descriptor = os.open(target, flags)
        except FileNotFoundError as exc:
            result["status"] = "changed"
            result["error_kind"] = "missing"
            result["error"] = str(exc) or "File disappeared"
            return result
        except PermissionError as exc:
            result["status"] = "unreadable"
            result["error_kind"] = "permission"
            result["error"] = str(exc) or "Permission denied"
            return result
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                result["status"] = "unsupported"
                result["error_kind"] = "link"
                result["error"] = "Symbolic links are not inspected."
            else:
                result["status"] = "unreadable"
                result["error_kind"] = "os"
                result["error"] = str(exc) or "Cannot open file"
            return result

        data = b""
        try:
            try:
                opened = os.fstat(descriptor)
            except OSError as exc:
                result["status"] = "unreadable"
                result["error_kind"] = "os"
                result["error"] = str(exc) or "Cannot validate file"
                return result

            if not stat_module.S_ISREG(opened.st_mode):
                result["status"] = "changed"
                result["error_kind"] = "changed"
                result["error"] = "Entry changed during inspection."
                return result
            if _changed(before, opened):
                result["status"] = "changed"
                result["error_kind"] = "changed"
                result["error"] = "File changed during inspection."
                return result

            chunks = []
            remaining = MAX_SIGNATURE_BYTES
            while remaining > 0:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass

        result["bytes_read"] = len(data)
        if not data:
            result["status"] = "empty"
            result["ok"] = True
            result["extension_match"] = "unknown"
            return result

        format_name = _match_signature(data)
        result["format"] = format_name
        result["format_label"] = _FORMAT_LABELS.get(format_name)
        result["extension_match"] = _extension_match(
            format_name, result["extension"]
        )
        if format_name is None:
            result["status"] = "unknown"
        else:
            result["status"] = "recognized"
        result["ok"] = True
        return result
