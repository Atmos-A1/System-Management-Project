"""Phase 4 cross-screen theme and accessibility checks."""

import inspect
import re
import sys
from datetime import datetime, timezone

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

import panther.ui.adaptive_control as adaptive_module
import panther.ui.battery as battery_module
import panther.ui.processes as processes_module
from panther.domain.models import ProcessIdentity, ProcessRecord
from panther.ui.adaptive_control import AdaptiveControlScreen
from panther.ui.battery import BatteryScreen
from panther.ui.design_system import DARK_COLORS, LIGHT_COLORS
from panther.ui.processes import ProcessesScreen
from panther.ui.theme import ThemeManager

HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")

PATCH_TARGETS = (
    adaptive_module,
    battery_module,
    processes_module,
)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def reset_stylesheet(app):
    yield
    app.setStyleSheet("")


def _record():
    return ProcessRecord(
        identity=ProcessIdentity(101, 100.0, "editor.exe", r"C:\Apps\editor.exe"),
        ppid=1,
        username="tester",
        status="running",
        cpu_percent=4.0,
        memory_rss=200 * 1024**2,
        memory_vms=400 * 1024**2,
        num_threads=4,
        first_seen=datetime.now(timezone.utc),
    )


def _patch_services(monkeypatch):
    monkeypatch.setattr(processes_module, "iter_process_records", lambda: [_record()])
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
    monkeypatch.setattr(
        battery_module,
        "get_battery_status",
        lambda: {"percent": 85, "secsleft": 5400, "power_plugged": False},
    )
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


def _build_screens(qtbot):
    processes = ProcessesScreen(process_loader=lambda: [_record()])
    battery = BatteryScreen()
    adaptive = AdaptiveControlScreen()
    battery.timer.stop()
    processes.killTimer(processes.refresh_timer)
    qtbot.addWidget(processes)
    qtbot.addWidget(battery)
    qtbot.addWidget(adaptive)
    qtbot.waitUntil(lambda: processes.table.state == "ready", timeout=3000)
    return processes, adaptive, battery


@pytest.mark.parametrize(
    "module", PATCH_TARGETS, ids=lambda module: module.__name__.split(".")[-1]
)
def test_phase4_screen_sources_have_no_literal_theme_colors(module):
    source = inspect.getsource(module)

    assert "setStyleSheet" not in source
    assert not HEX_COLOR.search(source)


def test_theme_switching_updates_already_created_screens(
    app, monkeypatch, qtbot
):
    _patch_services(monkeypatch)
    ThemeManager.apply_theme(app, "light")
    processes, adaptive, battery = _build_screens(qtbot)
    app.processEvents()

    for screen in (processes, adaptive, battery):
        assert screen.palette().color(QPalette.Window).name().lower() == (
            LIGHT_COLORS.background
        )

    ThemeManager.apply_theme(app, "dark")
    app.processEvents()
    app.processEvents()

    for screen in (processes, adaptive, battery):
        assert screen.palette().color(QPalette.Window).name().lower() == (
            DARK_COLORS.background
        )


def test_processes_is_accessible_and_keyboard_reachable(
    app, monkeypatch, qtbot
):
    _patch_services(monkeypatch)
    processes, _, _ = _build_screens(qtbot)

    assert processes.filter_bar.search_edit.accessibleName() != ""
    assert processes.filter_bar.search_edit.focusPolicy() != Qt.NoFocus
    assert processes.table.accessibleName() != ""
    assert processes.table.focusPolicy() != Qt.NoFocus
    assert processes.refresh_btn.accessibleName() != ""
    assert processes.refresh_btn.focusPolicy() != Qt.NoFocus
    assert processes.status_banner.message_label.accessibleName() != ""


def test_adaptive_control_is_accessible_and_cannot_enable_execution(
    app, monkeypatch, qtbot
):
    _patch_services(monkeypatch)
    _, adaptive, _ = _build_screens(qtbot)

    assert adaptive.mode.accessibleName() != ""
    assert adaptive.mode.focusPolicy() != Qt.NoFocus
    assert adaptive.rollback_button.accessibleName() != ""
    assert adaptive.app_list.accessibleName() != ""
    assert adaptive.recommendation_list.accessibleName() != ""
    assert adaptive.history_list.accessibleName() != ""
    assert adaptive.mode.model().item(2).isEnabled() is False


def test_battery_is_accessible_in_present_and_absent_states(
    app, monkeypatch, qtbot
):
    _patch_services(monkeypatch)
    _, _, battery = _build_screens(qtbot)

    assert battery.charge_card.value_label.accessibleName() != ""
    assert battery.status_card.value_label.accessibleName() != ""
    assert battery.runtime_card.value_label.accessibleName() != ""
    assert battery.unsupported_state.variant == "unsupported"
    assert battery.unsupported_state.accessibleName() != ""

    monkeypatch.setattr(battery_module, "get_battery_status", lambda: {})
    absent = BatteryScreen()
    absent.timer.stop()
    qtbot.addWidget(absent)

    assert absent.unsupported_state.accessibleName() != ""
    assert absent.unsupported_state.variant == "unsupported"
