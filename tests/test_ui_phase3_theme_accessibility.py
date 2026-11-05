"""Cross-screen light/dark and accessibility checks for the Phase 3 screens."""

import inspect
import re
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

import panther.ui.applications as applications_module
import panther.ui.dashboard as dashboard_module
import panther.ui.history as history_module
import panther.ui.startup as startup_module
from panther.ui.applications import ApplicationsScreen
from panther.ui.components import Badge, Sparkline
from panther.ui.dashboard import DashboardScreen
from panther.ui.design_system import DARK_COLORS, LIGHT_COLORS
from panther.ui.history import HistoryScreen
from panther.ui.startup import StartupScreen
from panther.ui.theme import ThemeManager

HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")

PATCH_TARGETS = (
    dashboard_module,
    applications_module,
    history_module,
    startup_module,
)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def reset_stylesheet(app):
    yield
    app.setStyleSheet("")


def _patch_all_services(monkeypatch):
    monkeypatch.setattr(dashboard_module, "get_cpu_percent", lambda: 12.5)
    monkeypatch.setattr(
        dashboard_module,
        "get_ram_usage",
        lambda: {"used": 2 * 1024**3, "total": 8 * 1024**3, "percent": 25.0},
    )
    monkeypatch.setattr(
        dashboard_module,
        "get_disk_usage",
        lambda: {"used": 6 * 1024**3, "total": 8 * 1024**3, "percent": 75.0},
    )
    monkeypatch.setattr(
        dashboard_module,
        "get_battery_info",
        lambda: {"percent": 55, "power_plugged": True},
    )
    monkeypatch.setattr(applications_module, "winreg", object())
    monkeypatch.setattr(
        applications_module,
        "get_installed_apps",
        lambda: [
            {
                "name": "Panther",
                "publisher": "Panther Labs",
                "version": "1.0",
                "install_location": "C:/Panther",
            }
        ],
    )
    monkeypatch.setattr(
        startup_module,
        "get_startup_entries",
        lambda: [
            {
                "name": "Panther",
                "command": "C:\\Panther\\PantherApp.exe",
                "scope": "HKCU",
                "enabled": True,
            }
        ],
    )
    monkeypatch.setattr(
        history_module,
        "get_recent",
        lambda limit=100: [
            (1, "2026-01-01T00:00:00", "storage", "Moved 3 files")
        ],
    )


def _build_screens():
    dashboard = DashboardScreen()
    dashboard.timer.stop()
    applications = ApplicationsScreen()
    startup = StartupScreen()
    history = HistoryScreen()
    history.timer.stop()
    return dashboard, applications, startup, history


@pytest.mark.parametrize(
    "module", PATCH_TARGETS, ids=lambda module: module.__name__.split(".")[-1]
)
def test_phase3_screen_sources_have_no_literal_theme_colors(module):
    source = inspect.getsource(module)

    assert "setStyleSheet" not in source
    assert not HEX_COLOR.search(source)


def test_theme_switching_updates_already_created_screens(app, monkeypatch):
    _patch_all_services(monkeypatch)
    ThemeManager.apply_theme(app, "light")
    screens = _build_screens()
    app.processEvents()

    for screen in screens:
        assert screen.palette().color(QPalette.Window).name().lower() == (
            LIGHT_COLORS.background
        )
    assert screens[0].cpu_card.sparkline.theme == "light"

    ThemeManager.apply_theme(app, "dark")
    app.processEvents()
    app.processEvents()

    for screen in screens:
        assert screen.palette().color(QPalette.Window).name().lower() == (
            DARK_COLORS.background
        )
    assert screens[0].cpu_card.sparkline.theme == "dark"


def test_all_four_screens_are_accessible_and_keyboard_reachable(
    app, monkeypatch
):
    _patch_all_services(monkeypatch)
    dashboard, applications, startup, history = _build_screens()

    # Dashboard controls.
    assert isinstance(dashboard.health_badge, Badge)
    assert dashboard.health_badge.focusPolicy() == Qt.NoFocus
    assert dashboard.refresh_button.accessibleName() != ""
    assert dashboard.refresh_button.focusPolicy() != Qt.NoFocus
    assert isinstance(dashboard.cpu_card.sparkline, Sparkline)
    assert dashboard.cpu_card.sparkline.focusPolicy() == Qt.NoFocus

    # Data screens: a labelled search field and a labelled, focusable table.
    for screen in (applications, startup, history):
        assert screen.filter_bar.search_edit.accessibleName() != ""
        assert screen.filter_bar.search_edit.focusPolicy() != Qt.NoFocus
        assert screen.table.accessibleName() != ""
        assert screen.table.focusPolicy() != Qt.NoFocus

    # Unsupported / empty panels carry their message as the accessible name.
    from panther.ui.components import EmptyState

    unsupported = EmptyState("Requires Windows", variant="unsupported")
    assert unsupported.accessibleName() == "Requires Windows"

    # Tests must not rely on colour alone: history details include a text badge.
    history.table.selectRow(0)
    assert history.details_badge.text()
    assert history.details_badge.accessibleName() != ""
