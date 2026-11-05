"""Tests for MainWindow theme integration and responsive shell layout."""

import sys
import types

import pytest
from PySide6.QtWidgets import QApplication, QSizePolicy

from panther.config import config
from panther.ui.design_system import DARK_COLORS, LIGHT_COLORS
from panther.ui.settings import SettingsScreen


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def restore_theme_config(app):
    original_theme = config.theme
    yield
    config.theme = original_theme
    app.setStyleSheet("")


@pytest.fixture
def main_window_cls(monkeypatch):
    """Import MainWindow with a winreg shim on non-Windows test hosts.

    Panther is a Windows-first application; ``startup_adapter`` and
    ``app_inventory`` import the Windows-only ``winreg`` module.  The real
    modules are used on Windows.  On Linux we provide the constants needed
    at import time so the shell tests can run; no registry calls occur
    because the affected screens are lazily constructed and are not visited.
    """

    if sys.platform != "win32":
        fake_winreg = types.ModuleType("winreg")
        fake_winreg.HKEY_CURRENT_USER = 0x80000001
        fake_winreg.HKEY_LOCAL_MACHINE = 0x80000002
        fake_winreg.KEY_READ = 0x20019
        fake_winreg.KEY_WRITE = 0x20006
        fake_winreg.KEY_WOW64_64KEY = 0x0100
        fake_winreg.OpenKey = lambda *args, **kwargs: (_ for _ in ()).throw(OSError())
        fake_winreg.EnumKey = lambda *args, **kwargs: (_ for _ in ()).throw(OSError())
        fake_winreg.EnumValue = lambda *args, **kwargs: (_ for _ in ()).throw(OSError())
        fake_winreg.QueryValueEx = lambda *args, **kwargs: (_ for _ in ()).throw(OSError())
        fake_winreg.DeleteValue = lambda *args, **kwargs: None
        monkeypatch.setitem(sys.modules, "winreg", fake_winreg)

    from panther.ui.main_window import MainWindow

    yield MainWindow

    if sys.platform != "win32":
        # Drop modules that captured the import-time winreg shim so later
        # tests can install their own fake winreg and re-import cleanly.
        for module_name in (
            "panther.ui.main_window",
            "panther.ui.startup",
            "panther.ui.applications",
            "panther.services.startup_adapter",
            "panther.services.app_inventory",
        ):
            sys.modules.pop(module_name, None)


def test_main_window_applies_configured_dark_theme(app, qtbot, monkeypatch, main_window_cls):
    monkeypatch.setattr(config, "theme", "dark")

    window = main_window_cls()
    qtbot.addWidget(window)

    assert window.resolved_theme == "dark"
    assert DARK_COLORS.background in app.styleSheet()
    assert window.sidebar.objectName() == "sidebar"
    assert window.stack.objectName() == "mainStack"


def test_main_window_applies_configured_light_theme(app, qtbot, monkeypatch, main_window_cls):
    monkeypatch.setattr(config, "theme", "light")

    window = main_window_cls()
    qtbot.addWidget(window)

    assert window.resolved_theme == "light"
    assert LIGHT_COLORS.background in app.styleSheet()


def test_sidebar_is_responsive_and_central_content_can_expand(app, qtbot, monkeypatch, main_window_cls):
    monkeypatch.setattr(config, "theme", "light")

    window = main_window_cls()
    qtbot.addWidget(window)

    sidebar = window.sidebar
    assert sidebar.minimumWidth() == 200
    assert sidebar.maximumWidth() == 260
    assert sidebar.width() <= sidebar.maximumWidth()
    assert sidebar.sizePolicy().horizontalPolicy() in (
        QSizePolicy.Fixed,
        QSizePolicy.Maximum,
    )

    layout = window.centralWidget().layout()
    assert layout.stretch(layout.indexOf(window.stack)) == 1
    assert window.stack.sizePolicy().horizontalPolicy() == QSizePolicy.Expanding


def test_main_window_enforces_a_usable_minimum_size(app, qtbot, monkeypatch, main_window_cls):
    monkeypatch.setattr(config, "theme", "light")

    window = main_window_cls()
    qtbot.addWidget(window)

    assert window.minimumWidth() >= 800
    assert window.minimumHeight() >= 550


def test_sidebar_items_receive_icons(app, qtbot, monkeypatch, main_window_cls):
    monkeypatch.setattr(config, "theme", "light")

    window = main_window_cls()
    qtbot.addWidget(window)

    assert window.sidebar.count() > 0
    for row in range(window.sidebar.count()):
        assert not window.sidebar.item(row).icon().isNull()



def test_lazy_screen_loading_is_preserved(app, qtbot, monkeypatch, main_window_cls):
    monkeypatch.setattr(config, "theme", "light")

    window = main_window_cls()
    qtbot.addWidget(window)

    # Dashboard is the initial screen and is therefore constructed.
    assert 0 in window._screen_widgets
    # Settings has not been visited yet.
    assert 9 not in window._screen_widgets

    window.sidebar.setCurrentRow(9)

    assert 9 in window._screen_widgets
    assert isinstance(window._screen_widgets[9], SettingsScreen)
    assert window.stack.currentIndex() == 9


def test_settings_theme_control_includes_system_and_applies_changes(
    app, qtbot, monkeypatch
):
    monkeypatch.setattr(config, "theme", "system")

    screen = SettingsScreen()
    qtbot.addWidget(screen)

    assert [screen.theme_combo.itemText(i) for i in range(screen.theme_combo.count())] == [
        "System",
        "Light",
        "Dark",
    ]
    assert screen.theme_combo.currentText() == "System"

    screen.theme_combo.setCurrentText("Dark")

    assert config.theme == "dark"
    assert DARK_COLORS.background in app.styleSheet()

    screen.theme_combo.setCurrentText("Light")

    assert config.theme == "light"
    assert LIGHT_COLORS.background in app.styleSheet()


def test_settings_preserves_refresh_interval_control(app, qtbot, monkeypatch):
    monkeypatch.setattr(config, "theme", "light")

    screen = SettingsScreen()
    qtbot.addWidget(screen)

    assert screen.refresh_spin.minimum() == 1
    assert screen.refresh_spin.maximum() == 60
    assert screen.refresh_spin.suffix() == " seconds"
