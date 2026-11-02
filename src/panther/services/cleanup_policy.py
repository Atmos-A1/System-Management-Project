"""Path safety rules for Storage cleanup.

Policies are pure and can be exercised with simulated Windows paths. Filesystem
preflight additionally checks that a target is an existing regular file and not
a symbolic link or Windows reparse point.
"""

import ntpath
import os
import posixpath
import stat
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


_PROTECTED_FILE_NAMES = {
    "pagefile.sys",
    "hiberfil.sys",
    "swapfile.sys",
    "bootmgr",
    "bootnxt",
}


@dataclass(frozen=True)
class CleanupDecision:
    path: str
    allowed: bool
    reason: str = ""


def _is_windows(windows: Optional[bool]) -> bool:
    return os.name == "nt" if windows is None else windows


def _canonical_parts(
    path: str, windows: Optional[bool] = None
) -> Tuple[str, Tuple[str, ...]]:
    """Return a drive/root and case-normalised path components.

    Components are compared as tuples so a sibling such as
    ``C:\\Windows.old`` or ``C:\\Downloads2`` cannot match a prefix by string
    accident.
    """
    if _is_windows(windows):
        normalized = ntpath.normpath(str(path))
        drive, tail = ntpath.splitdrive(normalized)
        parts = tuple(
            part.casefold()
            for part in tail.replace("/", "\\").split("\\")
            if part and part != "."
        )
        return drive.casefold(), parts

    normalized = posixpath.normpath(posixpath.abspath(str(path)))
    parts = tuple(part for part in normalized.split("/") if part)
    return "/", parts


def is_within(
    path: str, root: str, windows: Optional[bool] = None
) -> bool:
    path_drive, path_parts = _canonical_parts(path, windows)
    root_drive, root_parts = _canonical_parts(root, windows)
    if path_drive != root_drive:
        return False
    if len(path_parts) < len(root_parts):
        return False
    return path_parts[: len(root_parts)] == root_parts


def _is_volume_root(path: str, windows: Optional[bool] = None) -> bool:
    drive, parts = _canonical_parts(path, windows)
    return not parts and bool(drive)


def default_protected_roots(
    windows: Optional[bool] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> List[str]:
    is_windows = _is_windows(windows)
    env = os.environ if environ is None else environ

    if not is_windows:
        return [
            "/etc",
            "/bin",
            "/sbin",
            "/usr",
            "/lib",
            "/lib64",
            "/boot",
            "/proc",
            "/sys",
            "/dev",
            "/var/lib",
            "/root",
        ]

    drive = env.get("SystemDrive") or "C:"
    windows_root = env.get("SystemRoot") or ntpath.join(drive, "Windows")
    program_files = env.get("ProgramFiles") or ntpath.join(
        drive, "Program Files"
    )
    program_files_x86 = env.get("ProgramFiles(x86)") or ntpath.join(
        drive, "Program Files (x86)"
    )
    program_data = env.get("ProgramData") or ntpath.join(
        drive, "ProgramData"
    )

    roots = [
        windows_root,
        ntpath.join(windows_root, "System32"),
        ntpath.join(windows_root, "SysWOW64"),
        ntpath.join(windows_root, "WinSxS"),
        program_files,
        program_files_x86,
        program_data,
        ntpath.join(drive, "$Recycle.Bin"),
        ntpath.join(drive, "System Volume Information"),
        ntpath.join(drive, "Recovery"),
        ntpath.join(drive, "Boot"),
        ntpath.join(drive, "EFI"),
    ]

    user_profile = env.get("USERPROFILE")
    if user_profile:
        roots.append(ntpath.join(user_profile, "AppData"))

    return roots


def is_protected_path(
    path: str,
    windows: Optional[bool] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    if _is_volume_root(path, windows):
        return True

    for root in default_protected_roots(windows, environ):
        if is_within(path, root, windows):
            return True

    _, parts = _canonical_parts(path, windows)
    if parts and parts[-1].casefold() in _PROTECTED_FILE_NAMES:
        return True

    return False


def path_rejection_reason(
    path: str,
    allowed_roots: Iterable[str],
    windows: Optional[bool] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Return a rejection reason, or None when path policy permits review."""
    if _is_volume_root(path, windows):
        return "Path is a protected volume root"
    if is_protected_path(path, windows, environ):
        return "Path is in a protected system or application location"

    roots = [str(root) for root in allowed_roots if root]
    if not roots:
        return "No approved scan root"
    if not any(is_within(path, root, windows) for root in roots):
        return "Outside approved scan roots"
    return None


def _is_link_or_reparse(stat_result) -> bool:
    if stat.S_ISLNK(stat_result.st_mode):
        return True
    attributes = getattr(stat_result, "st_file_attributes", 0) or 0
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _absolute_path(path: str, windows: Optional[bool]) -> str:
    if _is_windows(windows):
        return ntpath.abspath(str(path))
    return posixpath.abspath(str(path))


def _resolved_path(path: str) -> str:
    try:
        return os.path.realpath(path)
    except OSError:
        return path


def _parent_path(path: str, windows: Optional[bool]) -> str:
    if _is_windows(windows):
        return ntpath.dirname(path)
    return posixpath.dirname(path)


def _ancestor_rejection_reason(
    target: str,
    allowed_roots: Sequence[str],
    windows: Optional[bool] = None,
) -> Optional[str]:
    """Reject link/reparse ancestors and physical escapes from approved roots."""
    absolute_target = _absolute_path(target, windows)
    resolved_target = _resolved_path(absolute_target)

    for root in allowed_roots:
        if not root:
            continue
        absolute_root = _absolute_path(str(root), windows)
        if not is_within(absolute_target, absolute_root, windows):
            continue

        try:
            root_stat = os.lstat(absolute_root)
        except OSError as exc:
            return f"Cannot inspect approved root: {exc}"
        if _is_link_or_reparse(root_stat):
            return (
                "Approved scan root is a symbolic link or reparse point"
            )

        root_key = _canonical_parts(absolute_root, windows)
        current = _parent_path(absolute_target, windows)
        while _canonical_parts(current, windows) != root_key:
            if not is_within(current, absolute_root, windows):
                break
            if current == absolute_root:
                break
            try:
                stat_result = os.lstat(current)
            except OSError as exc:
                return f"Cannot inspect parent path: {exc}"
            if _is_link_or_reparse(stat_result):
                return (
                    "Path contains a symbolic link or reparse point"
                )
            parent = _parent_path(current, windows)
            if parent == current:
                break
            current = parent

        resolved_root = _resolved_path(absolute_root)
        if not is_within(resolved_target, resolved_root, windows):
            return "Resolved path escapes approved scan root"
        return None

    return "Outside approved scan roots"


def inspect_path(
    path: str,
    allowed_roots: Sequence[str],
    windows: Optional[bool] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> CleanupDecision:
    """Run advisory filesystem and policy preflight for one path."""
    target = str(path)
    try:
        stat_result = os.lstat(target)
    except FileNotFoundError:
        return CleanupDecision(target, False, "Path does not exist")
    except OSError as exc:
        return CleanupDecision(target, False, f"Cannot inspect path: {exc}")

    if _is_link_or_reparse(stat_result):
        return CleanupDecision(
            target,
            False,
            "Symbolic links and reparse points cannot be cleaned",
        )
    if not stat.S_ISREG(stat_result.st_mode):
        return CleanupDecision(
            target, False, "Only regular files can be cleaned"
        )

    reason = path_rejection_reason(target, allowed_roots, windows, environ)
    if reason is not None:
        return CleanupDecision(target, False, reason)

    absolute_target = _absolute_path(target, windows)
    resolved_target = _resolved_path(absolute_target)
    if is_protected_path(resolved_target, windows, environ):
        return CleanupDecision(
            target,
            False,
            "Resolved path is in a protected system or application location",
        )

    reason = _ancestor_rejection_reason(
        target, allowed_roots, windows
    )
    if reason is not None:
        return CleanupDecision(target, False, reason)
    return CleanupDecision(target, True, "")


def inspect_paths(
    paths: Iterable[str],
    allowed_roots: Sequence[str],
    windows: Optional[bool] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> List[CleanupDecision]:
    return [
        inspect_path(path, allowed_roots, windows, environ) for path in paths
    ]
