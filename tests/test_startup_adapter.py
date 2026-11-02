import builtins
import sys
import types
import pytest

# We'll monkeypatch winreg module functions used in the adapter.

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
    return fake

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
