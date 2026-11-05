"""Rendered-contrast checks for the Phase 4 screens in both appearances."""

import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QPoint, QRect
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

import panther.ui.battery as battery_module
import panther.ui.processes as processes_module
from panther.domain.models.workload import WorkloadClassification
from panther.ui.adaptive_control import AdaptiveControlScreen
from panther.ui.battery import BatteryScreen
from panther.ui.processes import ProcessesScreen
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


@pytest.fixture(autouse=True)
def dispose_screens(app):
    """Delete contrast-test widgets before the next module applies a theme."""

    yield
    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QApplication.processEvents()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()


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


def _sample_snapshot():
    return {
        "system": SimpleNamespace(
            cpu_percent=17.5,
            memory_percent=63.0,
            memory_available=5 * 1024**3,
            timestamp=datetime.now(timezone.utc),
        ),
        "workload": WorkloadClassification(
            "heavy_memory", 0.9, ["measured memory pressure"], "high", 5,
            datetime.now(timezone.utc),
        ),
        "recommendations": [],
        "applications": [],
    }


def _patch_battery(monkeypatch, status):
    monkeypatch.setattr(battery_module, "get_battery_status", lambda: status)
    monkeypatch.setattr(battery_module, "get_processes", lambda: [])
    monkeypatch.setattr(
        battery_module,
        "classify_process",
        lambda process: {
            "category": "User application",
            "risk_level": "Medium",
            "explanation": "Test classification",
            "can_terminate": False,
        },
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_processes_text_contrast(app, monkeypatch, theme, qtbot):
    ThemeManager.apply_theme(app, theme)
    monkeypatch.setattr(
        processes_module.ProcessClassifier,
        "classify",
        lambda self, process: {
            "category": "User application",
            "risk_level": "Medium",
            "confidence": 0.6,
            "explanation": "Test classification",
            "evidence": [],
            "can_terminate": False,
        },
    )
    screen = ProcessesScreen(process_loader=lambda: [])
    qtbot.addWidget(screen)
    qtbot.waitUntil(lambda: screen.table.state == "empty", timeout=3000)
    screen.resize(1000, 700)

    assert _measure(screen, screen.scaffold.header.title_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.scaffold.header.subtitle_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.process_count_card.title_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.process_count_card.value_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.status_banner.message_label) >= BODY_TEXT_RATIO
    assert (
        _measure(screen, screen.table.empty_state.title_label) >= BODY_TEXT_RATIO
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_adaptive_control_text_contrast(app, theme, monkeypatch):
    ThemeManager.apply_theme(app, theme)
    # The contrast check only needs deterministic rendered content; it must not
    # start the real background sampler when the widget is shown.
    monkeypatch.setattr(AdaptiveControlScreen, "refresh", lambda self: None)
    screen = AdaptiveControlScreen()
    screen._on_sample_ready(_sample_snapshot())
    screen.resize(1240, 820)

    assert _measure(screen, screen.scaffold.header.title_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.scaffold.header.subtitle_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.cpu_card.title_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.cpu_card.value_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.status_banner.message_label) >= BODY_TEXT_RATIO
    assert (
        _measure(screen, screen.recommendations_card.title_label)
        >= BODY_TEXT_RATIO
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_battery_present_text_contrast(app, monkeypatch, theme):
    _patch_battery(
        monkeypatch,
        {"percent": 85, "secsleft": 5400, "power_plugged": False},
    )
    ThemeManager.apply_theme(app, theme)
    screen = BatteryScreen()
    screen.timer.stop()
    screen.resize(1000, 700)

    assert _measure(screen, screen.scaffold.header.title_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.scaffold.header.subtitle_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.charge_card.title_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.charge_card.value_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.charge_card.detail_label) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.details.label_for("Runtime source")) >= BODY_TEXT_RATIO
    assert _measure(screen, screen.details.value_label("Runtime source")) >= BODY_TEXT_RATIO


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_battery_unsupported_text_contrast(app, monkeypatch, theme):
    _patch_battery(monkeypatch, {})
    ThemeManager.apply_theme(app, theme)
    screen = BatteryScreen()
    screen.timer.stop()
    screen.resize(900, 600)

    assert (
        _measure(screen, screen.unsupported_state.title_label) >= BODY_TEXT_RATIO
    )
    assert (
        _measure(screen, screen.unsupported_state.description_label)
        >= BODY_TEXT_RATIO
    )
