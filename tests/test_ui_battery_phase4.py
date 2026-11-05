"""Phase 4 migration and safety tests for the Battery screen."""

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

import panther.ui.battery as battery_module
from panther.ui.battery import BatteryScreen
from panther.ui.components import (
    EmptyState,
    KeyValueList,
    MetricCard,
    PageScaffold,
    SectionCard,
)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def reset_stylesheet(app):
    yield
    app.setStyleSheet("")


def battery_status(percent=85, secsleft=5400, plugged=False):
    return {
        "percent": percent,
        "secsleft": secsleft,
        "power_plugged": plugged,
    }


def processes():
    return [
        {"pid": 10, "name": "editor.exe", "cpu_percent": 4.0, "memory_rss": 200 * 1024**2},
        {"pid": 4, "name": "System", "cpu_percent": 0.0, "memory_rss": 1024 * 1024},
    ]


def no_battery(monkeypatch):
    monkeypatch.setattr(battery_module, "get_battery_status", lambda: {})
    monkeypatch.setattr(battery_module, "get_processes", processes)


def with_battery(monkeypatch, status=None, procs=None):
    monkeypatch.setattr(
        battery_module, "get_battery_status", lambda: status or battery_status()
    )
    monkeypatch.setattr(battery_module, "get_processes", lambda: list(procs or processes()))
    monkeypatch.setattr(
        battery_module,
        "classify_process",
        lambda process: {
            "category": "User application"
            if process.get("name") != "System"
            else "Critical system component",
            "risk_level": "Medium" if process.get("name") != "System" else "Very High",
            "explanation": "Test classification",
            "can_terminate": process.get("name") != "System",
        },
    )


def test_battery_uses_scaffold_cards_and_section(app, monkeypatch):
    no_battery(monkeypatch)
    screen = BatteryScreen()
    screen.timer.stop()

    assert screen.objectName() == "batteryScreen"
    assert isinstance(screen.scaffold, PageScaffold)
    assert screen.scaffold.header.title_label.text() == "Battery & Power"
    assert isinstance(screen.charge_card, MetricCard)
    assert isinstance(screen.status_card, MetricCard)
    assert isinstance(screen.runtime_card, MetricCard)
    assert isinstance(screen.details_card, SectionCard)
    assert isinstance(screen.details, KeyValueList)
    assert isinstance(screen.unsupported_state, EmptyState)


def test_battery_present_state_shows_measured_and_estimated_values(app, monkeypatch):
    with_battery(monkeypatch)
    screen = BatteryScreen()
    screen.timer.stop()

    assert screen.state_stack.currentWidget() is screen.content
    assert screen.charge_card.value_label.text() == "85%"
    assert screen.charge_card.detail_label.text() == "Measured charge level"
    assert screen.status_card.value_label.text() == "Discharging"
    assert screen.runtime_card.value_label.text() == "1 hr 30 min left"
    assert screen.runtime_card.detail_label.text() == "Estimated time remaining (system)"
    assert screen.details.value("Reported charge") == "85% (measured)"
    assert screen.details.value("Runtime source") == "System estimate"


def test_battery_charging_state_is_explicit(app, monkeypatch):
    with_battery(monkeypatch, status=battery_status(percent=64, secsleft=4294967295, plugged=True))
    screen = BatteryScreen()
    screen.timer.stop()

    assert screen.status_card.value_label.text() == "Charging"
    assert screen.runtime_card.value_label.text() == "Plugged in"
    assert screen.runtime_card.detail_label.text() == "Charging from AC power"
    assert screen.details.value("Runtime source") == "Not applicable while charging"


def test_missing_battery_uses_unsupported_state_without_fabrication(app, monkeypatch):
    no_battery(monkeypatch)
    screen = BatteryScreen()
    screen.timer.stop()

    assert screen.state_stack.currentWidget() is screen.unsupported_state
    assert screen.unsupported_state.variant == "unsupported"
    text = (
        screen.unsupported_state.title_label.text()
        + " "
        + screen.unsupported_state.description_label.text()
    ).lower()
    assert "no battery" in text
    assert "not available" in text
    assert screen._top_procs == []
    assert screen.kill_buttons_layout.count() == 0


def test_unavailable_runtime_is_unknown_and_never_estimated(app, monkeypatch):
    with_battery(monkeypatch, status=battery_status(percent=50, secsleft=4294967295))
    screen = BatteryScreen()
    screen.timer.stop()

    assert screen.runtime_card.value_label.text() == "Unknown"
    assert screen.runtime_card.detail_label.text() == "Time estimate unavailable"
    assert screen.details.value("Runtime source") == "Unavailable"
    assert "hr left" not in screen.runtime_card.value_label.text()


def test_consumers_only_offer_buttons_for_terminable_processes(app, monkeypatch):
    with_battery(monkeypatch)
    screen = BatteryScreen()
    screen.timer.stop()

    assert len(screen.kill_buttons) == 1
    button = screen.kill_buttons[0]
    assert isinstance(button, QPushButton)
    assert "editor.exe" in button.text()
    assert button.accessibleName() != ""


def test_kill_requires_confirmation_then_uses_graceful_close(app, monkeypatch):
    with_battery(monkeypatch)
    calls = []
    monkeypatch.setattr(
        battery_module.process_action_manager,
        "graceful_close",
        lambda pid: calls.append(pid) or {"success": True, "message": "closed"},
    )
    monkeypatch.setattr(
        battery_module.QMessageBox, "warning", lambda *a, **k: QMessageBox.No
    )
    monkeypatch.setattr(
        battery_module.QMessageBox, "information", lambda *a, **k: None
    )

    screen = BatteryScreen()
    screen.timer.stop()
    screen._kill_consumer(10, processes()[0])

    assert calls == []

    monkeypatch.setattr(
        battery_module.QMessageBox, "warning", lambda *a, **k: QMessageBox.Yes
    )
    screen._kill_consumer(10, processes()[0])

    assert calls == [10]


def test_force_kill_requires_a_second_confirmation(app, monkeypatch):
    with_battery(monkeypatch)
    graceful, forced = [], []
    monkeypatch.setattr(
        battery_module.process_action_manager,
        "graceful_close",
        lambda pid: graceful.append(pid) or {"success": False, "needs_force": True},
    )
    monkeypatch.setattr(
        battery_module.process_action_manager,
        "force_kill",
        lambda pid: forced.append(pid) or {"success": True, "message": "killed"},
    )
    monkeypatch.setattr(
        battery_module.QMessageBox, "warning", lambda *a, **k: QMessageBox.Yes
    )
    monkeypatch.setattr(
        battery_module.QMessageBox, "question", lambda *a, **k: QMessageBox.No
    )
    monkeypatch.setattr(
        battery_module.QMessageBox, "information", lambda *a, **k: None
    )

    screen = BatteryScreen()
    screen.timer.stop()
    screen._kill_consumer(10, processes()[0])

    assert graceful == [10]
    assert forced == []

    monkeypatch.setattr(
        battery_module.QMessageBox, "question", lambda *a, **k: QMessageBox.Yes
    )
    screen._kill_consumer(10, processes()[0])

    assert forced == [10]


def test_battery_cards_are_keyboard_readable(app, monkeypatch):
    with_battery(monkeypatch)
    screen = BatteryScreen()
    screen.timer.stop()

    assert screen.charge_card.value_label.accessibleName() != ""
    assert screen.status_card.value_label.accessibleName() != ""
    assert screen.runtime_card.value_label.accessibleName() != ""
    assert screen.unsupported_state.focusPolicy() in (Qt.NoFocus, Qt.TabFocus)
