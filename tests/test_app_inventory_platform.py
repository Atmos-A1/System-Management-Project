"""Platform-safety tests for the application inventory service.

These mirror the startup adapter tests: importing the module must never crash
when ``winreg`` is unavailable, and the Windows registry path must keep working.
"""

import importlib
import sys
import types

import pytest

_MODULE = "panther.services.app_inventory"


@pytest.fixture
def isolated_module(monkeypatch):
    monkeypatch.delitem(sys.modules, _MODULE, raising=False)
    yield
    sys.modules.pop(_MODULE, None)


class _FakeKey:
    def __init__(self, children=None, values=None):
        self.children = children or {}
        self.values = values or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def EnumKey(self, index):
        names = list(self.children)
        if index >= len(names):
            raise OSError
        return names[index]

    def QueryValueEx(self, name):
        if name not in self.values:
            raise OSError
        return self.values[name], None


def test_inventory_imports_without_winreg_and_returns_no_apps(
    isolated_module, monkeypatch
):
    monkeypatch.setitem(sys.modules, "winreg", None)

    module = importlib.import_module(_MODULE)

    assert module.winreg is None
    assert module.get_installed_apps() == []


def test_inventory_still_reads_windows_registry(isolated_module, monkeypatch):
    app_key = _FakeKey(
        values={
            "DisplayName": "Panther",
            "Publisher": "Acme",
            "DisplayVersion": "1.0",
            "InstallLocation": r"C:\Panther",
        }
    )
    uninstall_key = _FakeKey(children={"Panther": app_key})
    machine_root = object()
    user_root = object()

    fake = types.SimpleNamespace(
        HKEY_LOCAL_MACHINE=machine_root,
        HKEY_CURRENT_USER=user_root,
        KEY_READ=0x20019,
    )

    def OpenKey(root, subkey, reserved=0, access=0):
        if root is uninstall_key:
            return uninstall_key.children[subkey]
        return uninstall_key

    fake.OpenKey = OpenKey
    fake.EnumKey = lambda key, index: key.EnumKey(index)
    fake.QueryValueEx = lambda key, name: key.QueryValueEx(name)
    monkeypatch.setitem(sys.modules, "winreg", fake)

    module = importlib.import_module(_MODULE)
    apps = module.get_installed_apps()

    assert apps == [
        {
            "name": "Panther",
            "publisher": "Acme",
            "version": "1.0",
            "install_location": r"C:\Panther",
        }
    ]
