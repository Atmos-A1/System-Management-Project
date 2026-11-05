"""Phase 4 migration and safety tests for Adaptive Control."""

import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import panther.ui.adaptive_control as adaptive_module
from panther.domain.models.policy import PolicyRecommendation
from panther.domain.models.resource_control import ControlAction
from panther.domain.models.workload import WorkloadClassification
from panther.ui.adaptive_control import AdaptiveControlScreen
from panther.ui.components import (
    MetricCard,
    PageScaffold,
    SectionCard,
    StatusBanner,
)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def reset_stylesheet(app):
    yield
    app.setStyleSheet("")


def workload(label="heavy_memory", confidence=0.9, pressure="high"):
    return WorkloadClassification(
        classification=label,
        confidence=confidence,
        evidence=["measured memory pressure"],
        pressure=pressure,
        samples_count=5,
        timestamp=datetime.now(timezone.utc),
    )


def sample_snapshot(recommendations=None, applications=None):
    system = SimpleNamespace(
        cpu_percent=17.5, memory_percent=63.0,
        memory_available=5 * 1024**3, timestamp=datetime.now(timezone.utc),
    )
    return {
        "system": system,
        "workload": workload(),
        "recommendations": recommendations or [],
        "applications": applications
        if applications is not None
        else [
            {"pid": 10, "name": "editor.exe", "cpu": 4.0,
             "memory": 200 * 1024**2, "category": "User application"},
        ],
    }


def recommendation():
    return PolicyRecommendation(
        id="rec-1",
        action_type="investigate",
        target_pid=None,
        target_name=None,
        reason="Sustained memory pressure",
        explanation="Review applications but Panther will not close anything.",
        confidence=0.9,
        measurement_quality=0.9,
        evidence=["measured memory pressure"],
    )


def action(reversible=True, result="success"):
    return ControlAction(
        id="action-1",
        action_type="set_priority",
        target_pid=42,
        target_name="editor.exe",
        previous_state={"priority": 32},
        new_state={"priority": 64},
        reason="User requested",
        mode="user_approved",
        reversible=reversible,
        timestamp=datetime.now(timezone.utc),
        result=result,
        verified=True,
    )


def test_adaptive_control_uses_scaffold_cards_and_banner():
    screen = AdaptiveControlScreen()

    assert screen.objectName() == "adaptiveControlScreen"
    assert isinstance(screen.scaffold, PageScaffold)
    assert screen.scaffold.header.title_label.text() == "Adaptive Resource Intelligence"
    assert isinstance(screen.cpu_card, MetricCard)
    assert isinstance(screen.memory_card, MetricCard)
    assert isinstance(screen.available_card, MetricCard)
    assert isinstance(screen.workload_card, MetricCard)
    assert isinstance(screen.pressure_card, MetricCard)
    assert isinstance(screen.status_banner, StatusBanner)
    assert isinstance(screen.applications_card, SectionCard)
    assert isinstance(screen.recommendations_card, SectionCard)
    assert isinstance(screen.history_card, SectionCard)


def test_adaptive_execution_mode_remains_unavailable():
    screen = AdaptiveControlScreen()

    assert screen.mode.count() == 3
    assert screen.mode.itemText(2) == "Adaptive Control (unavailable)"
    assert screen.mode.model().item(2).isEnabled() is False
    assert screen.mode.accessibleName() != ""
    assert screen.resource_controller._automatic_enabled is False


def test_adaptive_safeguards_are_not_weakened():
    screen = AdaptiveControlScreen()

    assert screen.policy_engine.config["auto_terminate"] is False
    assert screen.policy_engine.config["require_approval"] is True
    # The UI must not expose an action that can terminate a process.
    assert not hasattr(screen, "terminate_button")
    assert not hasattr(screen, "kill_button")


def test_sample_renders_metrics_lists_and_status():
    screen = AdaptiveControlScreen()
    screen.mode.setCurrentIndex(1)

    screen._on_sample_ready(
        sample_snapshot(
            recommendations=[recommendation()],
            applications=[
                {"pid": 10, "name": "editor.exe", "cpu": 4.0,
                 "memory": 200 * 1024**2, "category": "User application"},
                {"pid": 11, "name": "browser.exe", "cpu": 1.0,
                 "memory": 90 * 1024**2, "category": "User application"},
            ],
        )
    )

    assert screen.cpu_value.text() == "17.5%"
    assert screen.memory_value.text() == "63.0%"
    assert screen.available_value.text() == "5120 MiB"
    assert screen.workload_value.text() == "Heavy Memory"
    assert screen.pressure_value.text() == "High"
    assert screen.app_list.count() == 2
    assert screen.recommendation_list.count() == 1
    assert "Sustained memory pressure" in screen.recommendation_list.item(0).text()
    assert screen.status_banner.state in ("info", "success")
    assert "Updated" in screen.status_label.text()


def test_empty_sample_is_explicit_and_not_fabricated():
    screen = AdaptiveControlScreen()
    screen.mode.setCurrentIndex(1)

    screen._on_sample_ready(
        sample_snapshot(recommendations=[], applications=[])
    )

    assert screen.app_list.count() == 1
    assert "No verified user-application" in screen.app_list.item(0).text()
    assert screen.recommendation_list.count() == 1
    assert "No recommendation" in screen.recommendation_list.item(0).text()


def test_monitor_mode_does_not_show_actions():
    screen = AdaptiveControlScreen()
    screen._on_sample_ready(sample_snapshot(recommendations=[recommendation()]))
    screen.mode.setCurrentIndex(0)

    assert screen.recommendation_list.count() == 1
    text = screen.recommendation_list.item(0).text()
    assert "Monitor mode" in text


def test_measurement_failure_is_an_error_state():
    screen = AdaptiveControlScreen()

    screen._on_sample_failed("detector unavailable")

    assert screen.status_banner.state == "error"
    assert "detector unavailable" in screen.status_label.text()


def test_history_empty_state_and_rollback_guard(monkeypatch):
    screen = AdaptiveControlScreen()
    monkeypatch.setattr(screen.resource_controller, "get_history", lambda: [])

    screen._refresh_history()

    assert screen.history_list.count() == 1
    assert "No resource-control actions" in screen.history_list.item(0).text()
    assert screen.rollback_button.isEnabled() is False


def test_rollback_requires_confirmation_and_identity_verified_controller(
    monkeypatch,
):
    screen = AdaptiveControlScreen()
    pending = action()
    monkeypatch.setattr(screen.resource_controller, "get_history", lambda: [pending])
    screen._refresh_history()
    screen.history_list.setCurrentRow(0)

    assert screen.rollback_button.isEnabled() is True

    calls = []
    monkeypatch.setattr(
        adaptive_module.QMessageBox,
        "question",
        lambda *args, **kwargs: adaptive_module.QMessageBox.No,
    )
    monkeypatch.setattr(
        screen.resource_controller,
        "rollback",
        lambda action_id, user_confirmed=False: calls.append((action_id, user_confirmed))
        or (True, "restored"),
    )

    screen._rollback_selected()
    assert calls == []

    monkeypatch.setattr(
        adaptive_module.QMessageBox,
        "question",
        lambda *args, **kwargs: adaptive_module.QMessageBox.Yes,
    )
    monkeypatch.setattr(
        adaptive_module.QMessageBox, "information", lambda *args, **kwargs: None
    )
    screen._rollback_selected()

    assert calls == [("action-1", True)]


def test_history_only_enables_rollback_for_reversible_success(monkeypatch):
    screen = AdaptiveControlScreen()
    failed = action(reversible=True, result="failed")
    monkeypatch.setattr(screen.resource_controller, "get_history", lambda: [failed])
    screen._refresh_history()
    screen.history_list.setCurrentRow(0)

    assert screen.rollback_button.isEnabled() is False
