import builtins
import importlib
import sys
import types

import pytest

# We'll monkeypatch winreg module functions used in the adapter.

_ADAPTER_MODULE = "panther.services.startup_adapter"


@pytest.fixture
def isolated_adapter_module(monkeypatch):
    """Import a fresh adapter module and discard it after the test.

    Platform availability is decided when the module is imported, so tests
    that simulate a platform without ``winreg`` need their own module instance.
    """

    monkeypatch.delitem(sys.modules, _ADAPTER_MODULE, raising=False)
    yield
    sys.modules.pop(_ADAPTER_MODULE, None)

def _make_fake_key(values):
    """Return a simple object that mimics a registry key with EnumValue.
    *values* is a list of (name, command) tuples.
    """
    class FakeKey:
        def __init__(self, vals):
            self._vals = vals
        def EnumValue(self, index):
            if index < 0 or index >= len(self._vals):
                raise OSError
            name, cmd = self._vals[index]
            return (name, cmd, None)
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
    return FakeKey(values)

@pytest.fixture
def fake_winreg(monkeypatch):
    # Create a minimal fake winreg module with needed constants and functions.
    fake = types.SimpleNamespace()
    fake.HKEY_CURRENT_USER = 0x80000001
    fake.HKEY_LOCAL_MACHINE = 0x80000002
    fake.KEY_READ = 0x20019
    fake.KEY_WRITE = 0x20006
    # Simulate two entries in HKCU and none in HKLM.
    hkcu_key = _make_fake_key([("MyApp", r"C:\\Program Files\\MyApp\\myapp.exe")])
    def OpenKey(root, subkey, reserved=0, access=0):
        if root == fake.HKEY_CURRENT_USER:
            return hkcu_key
        raise PermissionError("Access denied for HKLM in test")
    fake.OpenKey = OpenKey
    fake.EnumValue = lambda key, i: key.EnumValue(i)
    fake.DeleteValue = lambda key, name: None
    monkeypatch.setitem(sys.modules, 'winreg', fake)
    # Importing the adapter binds ``winreg`` at import time.  Delete any cached
    # adapter module so the next import picks up the fake ``winreg`` from
    # ``sys.modules`` instead of a stale real module (Windows) or ``None``
    # (non-Windows).
    monkeypatch.delitem(sys.modules, _ADAPTER_MODULE, raising=False)
    yield fake
    # Teardown: remove the cached adapter module so subsequent tests do not
    # reuse an adapter bound to a stale (or real) ``winreg`` module.
    sys.modules.pop(_ADAPTER_MODULE, None)

def test_get_startup_entries(fake_winreg):
    from panther.services.startup_adapter import get_startup_entries
    entries = get_startup_entries()
    assert isinstance(entries, list)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["name"] == "MyApp"
    assert entry["scope"] == "HKCU"
    assert entry["enabled"] is True

def test_set_entry_disabled(fake_winreg):
    from panther.services.startup_adapter import set_entry_enabled
    # Should not raise when trying to disable existing entry.
    set_entry_enabled("MyApp", "HKCU", False)
    # Disabling a non‑existent entry should be a no‑op, not error.
    set_entry_enabled("NotThere", "HKCU", False)


def test_get_startup_entries_reads_both_hives(monkeypatch):
    fake = types.SimpleNamespace()
    fake.HKEY_CURRENT_USER = 0x80000001
    fake.HKEY_LOCAL_MACHINE = 0x80000002
    fake.KEY_READ = 0x20019
    fake.KEY_WRITE = 0x20006
    hkcu_key = _make_fake_key([("UserApp", r"C:\User\app.exe")])
    hklm_key = _make_fake_key([("MachineApp", r"C:\Machine\app.exe")])

    def OpenKey(root, subkey, reserved=0, access=0):
        return hkcu_key if root == fake.HKEY_CURRENT_USER else hklm_key

    fake.OpenKey = OpenKey
    fake.EnumValue = lambda key, i: key.EnumValue(i)
    fake.DeleteValue = lambda key, name: None
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.delitem(sys.modules, _ADAPTER_MODULE, raising=False)
    try:
        from panther.services.startup_adapter import get_startup_entries

        entries = get_startup_entries()
    finally:
        sys.modules.pop(_ADAPTER_MODULE, None)

    assert [entry["name"] for entry in entries] == ["UserApp", "MachineApp"]
    assert [entry["scope"] for entry in entries] == ["HKCU", "HKLM"]


def test_set_entry_enabled_enable_reports_missing_command(fake_winreg):
    from panther.services.startup_adapter import set_entry_enabled

    with pytest.raises(NotImplementedError):
        set_entry_enabled("MyApp", "HKCU", True)


def test_set_entry_enabled_rejects_unknown_scope(fake_winreg):
    from panther.services.startup_adapter import set_entry_enabled

    with pytest.raises(ValueError):
        set_entry_enabled("MyApp", "NOT_A_SCOPE", False)


def test_module_imports_and_reports_unsupported_without_winreg(
    isolated_adapter_module, monkeypatch
):
    # ``None`` in sys.modules makes ``import winreg`` raise ImportError, which
    # is how a non-Windows platform behaves.
    monkeypatch.setitem(sys.modules, "winreg", None)
    module = importlib.import_module(_ADAPTER_MODULE)

    assert module.winreg is None
    assert module._RUN_KEYS == []

    with pytest.raises(module.UnsupportedPlatformError) as error:
        module.get_startup_entries()

    message = str(error.value).lower()
    assert "windows" in message
    assert "not available" in message


def test_set_entry_enabled_reports_unsupported_without_winreg(
    isolated_adapter_module, monkeypatch
):
    monkeypatch.setitem(sys.modules, "winreg", None)
    module = importlib.import_module(_ADAPTER_MODULE)

    with pytest.raises(module.UnsupportedPlatformError):
        module.set_entry_enabled("MyApp", "HKCU", False)


def test_get_startup_entries_continues_on_per_scope_oserror(monkeypatch):
    """One scope raising FileNotFoundError/OSError still yields entries from the other scope."""
    fake = types.SimpleNamespace()
    fake.HKEY_CURRENT_USER = 0x80000001
    fake.HKEY_LOCAL_MACHINE = 0x80000002
    fake.KEY_READ = 0x20019
    fake.KEY_WRITE = 0x20006

    hkcu_key = _make_fake_key([("UserApp", r"C:\User\app.exe")])

    def OpenKey(root, subkey, reserved=0, access=0):
        if root == fake.HKEY_CURRENT_USER:
            return hkcu_key
        # Simulate HKLM key missing (FileNotFoundError) or other OSError
        raise FileNotFoundError("HKLM Run key not found")

    fake.OpenKey = OpenKey
    fake.EnumValue = lambda key, i: key.EnumValue(i)
    fake.DeleteValue = lambda key, name: None

    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.delitem(sys.modules, _ADAPTER_MODULE, raising=False)
    try:
        from panther.services.startup_adapter import get_startup_entries

        entries = get_startup_entries()
    finally:
        sys.modules.pop(_ADAPTER_MODULE, None)

    # Should get HKCU entry, not crash on HKLM failure
    assert len(entries) == 1
    assert entries[0]["name"] == "UserApp"
    assert entries[0]["scope"] == "HKCU"


def test_get_startup_entries_continues_on_plain_oserror(monkeypatch):
    """One scope raising plain OSError (not PermissionError/FileNotFoundError) still yields other scope."""
    fake = types.SimpleNamespace()
    fake.HKEY_CURRENT_USER = 0x80000001
    fake.HKEY_LOCAL_MACHINE = 0x80000002
    fake.KEY_READ = 0x20019
    fake.KEY_WRITE = 0x20006

    hkcu_key = _make_fake_key([("UserApp", r"C:\User\app.exe")])

    def OpenKey(root, subkey, reserved=0, access=0):
        if root == fake.HKEY_CURRENT_USER:
            return hkcu_key
        # Simulate a generic OSError (e.g., corruption, winerror 5, etc.)
        raise OSError("Generic registry error")

    fake.OpenKey = OpenKey
    fake.EnumValue = lambda key, i: key.EnumValue(i)
    fake.DeleteValue = lambda key, name: None

    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.delitem(sys.modules, _ADAPTER_MODULE, raising=False)
    try:
        from panther.services.startup_adapter import get_startup_entries

        entries = get_startup_entries()
    finally:
        sys.modules.pop(_ADAPTER_MODULE, None)

    assert len(entries) == 1
    assert entries[0]["name"] == "UserApp"
    assert entries[0]["scope"] == "HKCU"


def test_set_entry_enabled_wraps_oserror_in_registryoperationerror(monkeypatch):
    """set_entry_enabled wraps OSError in RegistryOperationError for service-level mapping."""
    fake = types.SimpleNamespace()
    fake.HKEY_CURRENT_USER = 0x80000001
    fake.HKEY_LOCAL_MACHINE = 0x80000002
    fake.KEY_READ = 0x20019
    fake.KEY_WRITE = 0x20006

    hkcu_key = _make_fake_key([])

    def OpenKey(root, subkey, reserved=0, access=0):
        if root == fake.HKEY_CURRENT_USER and access == fake.KEY_WRITE:
            raise PermissionError("Access denied for write")
        return hkcu_key

    fake.OpenKey = OpenKey
    fake.EnumValue = lambda key, i: key.EnumValue(i)
    fake.DeleteValue = lambda key, name: None

    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.delitem(sys.modules, _ADAPTER_MODULE, raising=False)
    try:
        from panther.services.startup_adapter import set_entry_enabled, RegistryOperationError

        with pytest.raises(RegistryOperationError) as exc_info:
            set_entry_enabled("MyApp", "HKCU", False)
        # Verify the original OSError is chained
        assert isinstance(exc_info.value.__cause__, PermissionError)
    finally:
        sys.modules.pop(_ADAPTER_MODULE, None)
