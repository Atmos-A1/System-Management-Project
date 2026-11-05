"""Dashboard tests for the Phase 3 design-system migration."""

import inspect
import re
import sys

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QScrollArea

import panther.ui.dashboard as dashboard_module
from panther.ui.components import Badge, MetricCard, PageScaffold, Sparkline, Toolbar
from panther.ui.dashboard import DashboardScreen
from panther.ui.design_system import DARK_COLORS
from panther.ui.theme import ThemeManager

HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def reset_stylesheet(app):
    yield
    app.setStyleSheet("")


def _patch_metrics(monkeypatch, cpu=12.5, ram_percent=25.0, disk_percent=75.0, battery=None):
    monkeypatch.setattr(dashboard_module, "get_cpu_percent", lambda: cpu)
    monkeypatch.setattr(
        dashboard_module,
        "get_ram_usage",
        lambda: {
            "used": 2 * 1024**3,
            "total": 8 * 1024**3,
            "percent": ram_percent,
        },
    )
    monkeypatch.setattr(
        dashboard_module,
        "get_disk_usage",
        lambda: {
            "used": 6 * 1024**3,
            "total": 8 * 1024**3,
            "percent": disk_percent,
        },
    )
    monkeypatch.setattr(
        dashboard_module,
        "get_battery_info",
        lambda: ({"percent": 55, "power_plugged": False} if battery is None else battery),
    )


def test_dashboard_uses_scaffold_scroll_and_metric_cards(app):
    screen = DashboardScreen()

    assert screen.objectName() == "dashboardScreen"
    assert isinstance(screen.scaffold, PageScaffold)
    assert screen.scaffold.header.title_label.text() == "System Dashboard"
    assert isinstance(screen.summary_bar, Toolbar)

    scroll = screen.findChild(QScrollArea)
    assert scroll is not None

    for attribute in ("cpu_card", "ram_card", "disk_card", "battery_card"):
        card = getattr(screen, attribute)
        assert isinstance(card, MetricCard)
        assert isinstance(card.sparkline, Sparkline)


def test_dashboard_has_health_summary_and_refresh_action(app):
    screen = DashboardScreen()

    assert isinstance(screen.health_badge, Badge)
    assert screen.health_badge.status in ("neutral", "success", "warning", "critical")
    assert screen.updated_label.text() != ""
    assert screen.refresh_button.accessibleName() != ""
    assert screen.refresh_button.focusPolicy() != 0


def test_dashboard_source_has_no_screen_level_theme_colors():
    source = inspect.getsource(dashboard_module)

    assert "setStyleSheet" not in source
    assert not HEX_COLOR.search(source)


def test_refresh_updates_values_progress_and_sparklines(app, monkeypatch):
    _patch_metrics(monkeypatch)

    screen = DashboardScreen()
    screen.refresh()
    screen.refresh()

    assert screen.cpu_card.value_label.text() == "12.5%"
    assert screen.ram_card.value_label.text() == "25.0%"
    assert screen.disk_card.value_label.text() == "75.0%"
    assert screen.battery_card.value_label.text() == "55%"
    assert screen.cpu_card.progress.value() == 12
    assert screen.ram_card.progress.value() == 25
    assert screen.disk_card.progress.value() == 75
    assert screen.battery_card.progress.value() == 55

    # Two samples are enough for a visible trend line.
    assert len(screen.cpu_card.sparkline.values()) >= 2
    assert len(screen.ram_card.sparkline.values()) >= 2
    assert len(screen.disk_card.sparkline.values()) >= 2


def test_refresh_reports_healthy_and_degraded_states(app, monkeypatch):
    _patch_metrics(monkeypatch)
    screen = DashboardScreen()
    screen.refresh()
    assert screen.health_badge.status == "success"

    def _fail():
        raise OSError("metrics unavailable")

    monkeypatch.setattr(dashboard_module, "get_cpu_percent", _fail)
    screen.refresh()

    assert screen.cpu_card.value_label.text() == "N/A"
    assert screen.cpu_card.detail_label.text() == "Unavailable"
    assert screen.health_badge.status == "critical"
    assert "unavailable" in screen.status_banner.message.lower()


def test_dashboard_handles_missing_battery_without_fake_data(app, monkeypatch):
    _patch_metrics(monkeypatch, battery={})

    screen = DashboardScreen()

    assert screen.battery_card.value_label.text() == "N/A"
    assert "No battery" in screen.battery_card.detail_label.text()


def test_theme_switch_updates_existing_dashboard_sparklines(app, monkeypatch):
    _patch_metrics(monkeypatch)
    ThemeManager.apply_theme(app, "light")
    screen = DashboardScreen()
    app.processEvents()

    assert screen.cpu_card.sparkline.theme == "light"

    screen.theme_combo = None  # guard: theme is switched elsewhere, not here
    ThemeManager.apply_theme(app, "dark")
    app.processEvents()

    assert screen.palette().color(QPalette.Window).name().lower() == (
        DARK_COLORS.background
    )
    assert screen.cpu_card.sparkline.theme == "dark"
