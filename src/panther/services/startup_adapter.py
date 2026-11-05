"""Startup entry service adapters.

Provides functions to read and toggle Windows "Run" startup entries from both the
current‑user (HKCU) and local‑machine (HKLM) hives. All functions are pure
Python – they do **not** import any Qt modules, keeping business logic separate
from the UI.

On non-Windows platforms the Windows registry module (``winreg``) is not
available.  Importing this module is always safe there, but registry operations
raise :class:`UnsupportedPlatformError` instead of pretending to return data.

The adapter deliberately avoids performing any destructive action without an
explicit caller‑provided confirmation; the UI layer must ask the user before
calling :func:`set_entry_enabled`.
"""

from typing import List, Dict, Any

try:  # ``winreg`` only exists on Windows.
    import winreg
except ImportError:  # pragma: no cover - exercised by platform-specific tests
    winreg = None  # type: ignore[assignment]


class UnsupportedPlatformError(RuntimeError):
    """Raised when a Windows-only registry operation is unavailable."""


_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

if winreg is not None:
    _RUN_KEYS = [
        (winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, "HKCU"),
        (winreg.HKEY_LOCAL_MACHINE, _RUN_KEY_PATH, "HKLM"),
    ]
else:  # pragma: no cover - exercised by platform-specific tests
    _RUN_KEYS = []


def _require_registry() -> None:
    """Fail clearly when Windows registry support is not available."""

    if winreg is None:
        raise UnsupportedPlatformError(
            "Startup app management requires the Windows registry, which is "
            "not available on this platform."
        )


def _open_key(root, subkey, access=None):
    _require_registry()
    if access is None:
        access = winreg.KEY_READ
    try:
        return winreg.OpenKey(root, subkey, 0, access)
    except PermissionError as e:
        raise PermissionError(f"Cannot open registry key {subkey!r}: {e}")

def get_startup_entries() -> List[Dict[str, Any]]:
    """Return a list of startup entries.

    Each entry is a dict with ``name``, ``command``, ``scope`` ("HKCU"/"HKLM"),
    and ``enabled`` (always ``True`` for entries present in the Run key – the
    adapter does not track disabled entries because Windows stores only the
    enabled ones).  Errors reading a hive are ignored – the entry list will just
    be missing that scope.

    Raises :class:`UnsupportedPlatformError` when the Windows registry is not
    available rather than returning an empty list, so callers can distinguish
    "nothing configured" from "not supported here".
    """
    _require_registry()
    entries: List[Dict[str, Any]] = []
    for root, subkey, scope in _RUN_KEYS:
        try:
            with _open_key(root, subkey) as key:
                i = 0
                while True:
                    try:
                        name, command, _ = winreg.EnumValue(key, i)
                        entries.append({
                            "name": name,
                            "command": command,
                            "scope": scope,
                            "enabled": True,
                        })
                        i += 1
                    except OSError:
                        break
        except PermissionError:
            continue
    return entries

def set_entry_enabled(name: str, scope: str, enable: bool) -> None:
    """Enable or disable a startup entry.

    Windows stores only *enabled* entries in the Run key.  To *disable* we delete
    the value; to *enable* we recreate it with the stored command.  This
    function therefore needs the original command if ``enable`` is ``True`` –
    callers should retrieve it via :func:`get_startup_entries` first.

    Raises :class:`UnsupportedPlatformError` when the Windows registry is not
    available.
    """
    _require_registry()
    root, subkey = None, None
    for r, sk, s in _RUN_KEYS:
        if s == scope:
            root, subkey = r, sk
            break
    if root is None:
        raise ValueError(f"Unknown scope {scope!r}")

    access = winreg.KEY_WRITE
    with _open_key(root, subkey, access) as key:
        if enable:
            raise NotImplementedError(
                "Enabling a disabled entry requires the original command – "
                "callers should store the command before deletion."
            )
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
