"""Phase 4 design-system migration tests for the Processes screen."""

import sys
import threading
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from panther.domain.models import ProcessIdentity, ProcessRecord
from panther.ui.components import (
    Badge,
    DataTable,
    FilterBar,
    MetricCard,
    PageScaffold,
    SectionCard,
    StatusBanner,
)
import panther.ui.processes as processes_module
from panther.ui.processes import ProcessesScreen

from datetime import datetime, timezone


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


@pytest.fixture(autouse=True)
def reset_stylesheet(app):
    yield
    app.setStyleSheet("")


@pytest.fixture(autouse=True)
def user_application_classifier(monkeypatch):
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


def make_record(pid=101, name="editor.exe", cpu=12.5, memory=20 * 1024 * 1024):
    return ProcessRecord(
        identity=ProcessIdentity(pid, 100.0, name, r"C:\Apps\{}".format(name)),
        ppid=1,
        username="tester",
        status="running",
        cpu_percent=cpu,
        memory_rss=memory,
        memory_vms=memory * 2,
        num_threads=4,
        first_seen=datetime.now(timezone.utc),
    )


def classifier(process):
    return {
        "category": "User application",
        "risk_level": "Medium",
        "confidence": 0.6,
        "explanation": "Test classification",
        "can_terminate": False,
    }


def wait_for(qtbot, predicate, timeout=3000):
    qtbot.waitUntil(predicate, timeout=timeout)


def test_processes_uses_scaffold_filter_bar_table_and_cards(qtbot):
    screen = ProcessesScreen(process_loader=lambda: [])
    qtbot.addWidget(screen)

    assert screen.objectName() == "processesScreen"
    assert isinstance(screen.scaffold, PageScaffold)
    assert screen.scaffold.header.title_label.text() == "Processes"
    assert isinstance(screen.filter_bar, FilterBar)
    assert screen.search_input is screen.filter_bar.search_edit
    assert isinstance(screen.table, DataTable)
    assert isinstance(screen.process_count_card, MetricCard)
    assert isinstance(screen.cpu_card, MetricCard)
    assert isinstance(screen.memory_card, MetricCard)
    assert isinstance(screen.status_banner, StatusBanner)
    assert isinstance(screen.details_card, SectionCard)


def test_processes_populated_state_uses_existing_models(qtbot):
    screen = ProcessesScreen(process_loader=lambda: [make_record()])
    qtbot.addWidget(screen)
    wait_for(qtbot, lambda: "Updated" in screen.status_label.text())

    assert screen.table.state == "ready"
    assert screen.model.rowCount() == 1
    assert screen.table.model() is screen.proxy
    assert screen.process_count_value.text() == "1"


def test_processes_empty_state_is_explicit(qtbot):
    screen = ProcessesScreen(process_loader=lambda: [])
    qtbot.addWidget(screen)
    wait_for(qtbot, lambda: screen.table.state == "empty")

    assert "No user applications" in screen.table.empty_state.title_label.text()
    assert screen.table.empty_state.isVisible() or not screen.isVisible()


def test_processes_loading_state_is_explicit(qtbot):
    release = threading.Event()

    def loader():
        release.wait(2)
        return [make_record()]

    screen = ProcessesScreen(process_loader=loader)
    qtbot.addWidget(screen)

    wait_for(qtbot, lambda: screen.table.state == "loading")
    assert "Loading process information" in screen.status_label.text()
    release.set()
    wait_for(qtbot, lambda: screen.table.state == "ready")


def test_processes_error_state_offers_retry(qtbot):
    calls = {"count": 0}

    def loader():
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("process provider failed")
        return [make_record()]

    screen = ProcessesScreen(process_loader=loader)
    qtbot.addWidget(screen)
    wait_for(qtbot, lambda: screen.table.state == "error")

    assert "process provider failed" in screen.table.error_state.description_label.text()
    assert screen.table.error_state.retry_button.focusPolicy() != Qt.NoFocus

    screen.table.error_state.retry_button.click()
    wait_for(qtbot, lambda: calls["count"] == 2 and screen.table.state == "ready")


def test_processes_filter_with_no_matches_shows_empty_state(qtbot):
    screen = ProcessesScreen(process_loader=lambda: [make_record()])
    qtbot.addWidget(screen)
    wait_for(qtbot, lambda: screen.table.state == "ready")

    screen.filter_bar.set_search_text("does-not-exist")
    wait_for(qtbot, lambda: screen.table.state == "empty")
    assert "No matching" in screen.table.empty_state.title_label.text()


def test_processes_details_use_badges_and_disabled_actions(qtbot):
    screen = ProcessesScreen(process_loader=lambda: [make_record()])
    qtbot.addWidget(screen)
    wait_for(qtbot, lambda: screen.table.state == "ready")

    screen.table.selectRow(0)

    assert isinstance(screen.details_badge, Badge)
    assert screen.details_badge.text()
    assert screen.details.value("PID") == "101"
    assert screen.close_btn.isEnabled() is False
    assert screen.force_kill_btn.isHidden() is True
    assert screen.close_btn.toolTip()


def test_processes_actions_never_dispatch_process_termination(qtbot, monkeypatch):
    dispatched = []
    monkeypatch.setattr(
        "panther.services.process_actions.process_action_manager.graceful_close",
        lambda pid: dispatched.append(pid) or {"success": True},
    )

    screen = ProcessesScreen(process_loader=lambda: [make_record()])
    qtbot.addWidget(screen)
    wait_for(qtbot, lambda: screen.table.state == "ready")
    screen.table.selectRow(0)
    screen.close_btn.click()
    screen.force_kill_btn.click()

    assert dispatched == []
