"""Rendered-contrast checks for the Phase 3 screens in both appearances."""

import sys

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

import panther.ui.applications as applications_module
import panther.ui.dashboard as dashboard_module
import panther.ui.history as history_module
import panther.ui.startup as startup_module
from panther.ui.applications import ApplicationsScreen
from panther.ui.dashboard import DashboardScreen
from panther.ui.history import HistoryScreen
from panther.ui.startup import StartupScreen
from panther.ui.theme import ThemeManager

BODY_TEXT_RATIO = 4.5


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def reset_stylesheet(app):
    yield
    app.setStyleSheet("")


def _relative_luminance(color: QColor) -> float:
    def channel(value):
        srgb = value / 255.0
        return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.red())
        + 0.7152 * channel(color.green())
        + 0.0722 * channel(color.blue())
    )


def _contrast(first: QColor, second: QColor) -> float:
    a, b = _relative_luminance(first), _relative_luminance(second)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def _dominant(image) -> QColor:
    counts = {}
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            key = (color.red(), color.green(), color.blue())
            counts[key] = counts.get(key, 0) + 1
    return QColor(*max(counts, key=counts.get))


def _measure(host, widget) -> float:
    host.adjustSize()
    host.show()
    QApplication.processEvents()
    image = host.grab().toImage()
    rect = QRect(widget.mapTo(host, QPoint(0, 0)), widget.size()).intersected(
        image.rect()
    )
    region = image.copy(rect)
    background = _dominant(region)
    best = 1.0
    for y in range(region.height()):
        for x in range(region.width()):
            best = max(best, _contrast(region.pixelColor(x, y), background))
    host.hide()
    return best


def _patch_services(monkeypatch):
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
        startup_module, "get_startup_entries", lambda: []
    )
    monkeypatch.setattr(
        history_module,
        "get_recent",
        lambda limit=100: [
            (1, "2026-01-01T00:00:00", "storage", "Moved 3 files")
        ],
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_dashboard_metric_text_contrast(app, monkeypatch, theme):
    _patch_services(monkeypatch)
    ThemeManager.apply_theme(app, theme)
    screen = DashboardScreen()
    screen.timer.stop()
    screen.resize(1240, 820)

    assert _measure(screen, screen.cpu_card.value_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.cpu_card.title_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.cpu_card.detail_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.scaffold.header.title_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.scaffold.header.subtitle_label) >= BODY_TEXT_RATIO


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_data_screen_text_and_state_contrast(app, monkeypatch, theme):
    _patch_services(monkeypatch)
    ThemeManager.apply_theme(app, theme)

    applications = ApplicationsScreen()
    startup = StartupScreen()
    history = HistoryScreen()
    history.timer.stop()

    for screen in (applications, startup, history):
        screen.resize(1000, 700)
        assert (
            _measure(screen, screen.scaffold.header.title_label)
            >= BODY_TEXT_RATIO
        )
        assert (
            _measure(screen, screen.scaffold.header.subtitle_label)
            >= BODY_TEXT_RATIO
        )

    assert (
        _measure(startup, startup.empty_state.title_label) >= BODY_TEXT_RATIO
    )
    assert (
        _measure(startup, startup.empty_state.description_label)
        >= BODY_TEXT_RATIO
    )

    history.table.selectRow(0)
    assert (
        _measure(history, history.details.value_label("Detail"))
        >= BODY_TEXT_RATIO
    )
    assert (
        _measure(history, history.details.label_for("Detail"))
        >= BODY_TEXT_RATIO
    )
    assert _measure(history, history.details_badge) >= BODY_TEXT_RATIO
