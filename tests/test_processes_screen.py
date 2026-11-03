import sys
from datetime import datetime, timezone
import threading
import time

import pytest
from PySide6.QtCore import Qt

from panther.domain.models import ProcessIdentity, ProcessRecord
from panther.services.windows_process_adapter import ProcessVerificationResult, ProcessVerificationStatus
from panther.ui.processes import (
    ProcessFilterProxyModel, ProcessLoadThread, ProcessTableModel, ProcessesScreen,
)


def make_record(pid=101, name="editor.exe", cpu=12.5, memory=20 * 1024 * 1024, create_time=100.0):
    return ProcessRecord(
        identity=ProcessIdentity(pid, create_time, name, r"C:\Apps\{}".format(name)),
        ppid=1, username="tester", status="running", cpu_percent=cpu,
        memory_rss=memory, memory_vms=memory * 2 if memory is not None else None,
        num_threads=4, first_seen=datetime.now(timezone.utc),
    )


class FakeVerifier:
    def inspect(self, identity):
        return ProcessVerificationResult(
            status=ProcessVerificationStatus.VERIFIED, requested_identity=identity,
            observed_create_time=identity.create_time, handle_closed=True, detail="Fake verification passed",
        )


def classifier(process):
    return {
        "category": "User application", "risk_level": "Medium", "confidence": 0.6,
        "explanation": "Test classification", "can_terminate": False,
    }


def test_table_model_preserves_unavailable_metrics(qtbot):
    model = ProcessTableModel()
    record = make_record(cpu=None, memory=None)
    process = {"pid": record.identity.pid, "name": record.identity.name,
               "cpu_percent": None, "memory_rss": None, "status": "running",
               "identity": record.identity}
    model.set_rows([(process, classifier(process))])
    assert model.data(model.index(0, 2), Qt.DisplayRole) == "—"
    assert model.data(model.index(0, 3), Qt.DisplayRole) == "—"


def test_proxy_filters_search_and_always_hides_non_user_processes(qtbot):
    model = ProcessTableModel()
    rows = []
    for record in (make_record(), make_record(102, "worker.exe", 2.0),
                   make_record(103, "service.exe", 4.0)):
        process = {"pid": record.identity.pid, "name": record.identity.name,
                   "exe": record.identity.exe, "cpu_percent": record.cpu_percent,
                   "memory_rss": record.memory_rss, "status": record.status,
                   "identity": record.identity}
        classification = classifier(process)
        if record.identity.pid == 103:
            classification = dict(classification, category="Important Windows service")
        rows.append((process, classification))
    model.set_rows(rows)
    proxy = ProcessFilterProxyModel()
    proxy.setSourceModel(model)
    assert proxy.filter_type == "All user applications"
    proxy.set_criteria("editor", "All user applications")
    assert proxy.rowCount() == 1
    proxy.set_criteria("", "All user applications")
    assert proxy.rowCount() == 2
    proxy.set_criteria("", "High Memory (>100 MiB)")
    assert proxy.rowCount() == 0
    proxy.set_criteria("missing", "All user applications")
    assert proxy.rowCount() == 0


def test_proxy_numeric_sort(qtbot):
    model = ProcessTableModel()
    rows = []
    for record in (make_record(9, "nine.exe", 9.0), make_record(10, "ten.exe", 10.0)):
        process = {"pid": record.identity.pid, "name": record.identity.name,
                   "cpu_percent": record.cpu_percent, "memory_rss": record.memory_rss,
                   "status": record.status, "identity": record.identity}
        rows.append((process, classifier(process)))
    model.set_rows(rows)
    proxy = ProcessFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.sort(1, Qt.AscendingOrder)
    assert proxy.data(proxy.index(0, 1), Qt.DisplayRole) == "9"
    assert proxy.data(proxy.index(1, 1), Qt.DisplayRole) == "10"


def test_loader_runs_off_gui_thread(qtbot):
    gui_thread = threading.get_ident()
    loader_threads = []
    def loader():
        loader_threads.append(threading.get_ident())
        return [make_record()]
    thread = ProcessLoadThread(loader=loader, classifier=classifier)
    batches = []
    thread.batch_ready.connect(batches.extend)
    with qtbot.waitSignal(thread.completed, timeout=3000):
        thread.start()
    thread.wait()
    assert loader_threads[0] != gui_thread
    assert len(batches) == 1


def test_screen_loads_asynchronously_and_disables_actions(qtbot):
    calls = []
    def loader():
        calls.append(threading.get_ident())
        time.sleep(0.05)
        return [make_record()]
    screen = ProcessesScreen(process_loader=loader, process_verifier=FakeVerifier())
    qtbot.addWidget(screen)
    qtbot.waitUntil(lambda: "Updated" in screen.status_label.text(), timeout=3000)
    assert len(calls) == 1
    assert screen.model.rowCount() == 1
    assert not screen.close_btn.isEnabled()
    assert not screen.force_kill_btn.isEnabled()


def test_duplicate_refresh_does_not_overlap(qtbot):
    calls = []
    def loader():
        calls.append(1)
        time.sleep(0.15)
        return [make_record()]
    screen = ProcessesScreen(process_loader=loader, process_verifier=FakeVerifier())
    qtbot.addWidget(screen)
    screen.refresh()
    screen.refresh()
    qtbot.waitUntil(lambda: "Updated" in screen.status_label.text(), timeout=3000)
    assert len(calls) == 1


@pytest.mark.xfail(
    sys.platform.startswith("linux"),
    strict=True,
    reason=(
        "Known upstream failure on Linux: selected_identity is not set "
        "after selectRow(0). Windows remains unmarked."
    ),
)
def test_selection_clears_when_pid_is_reused(qtbot):
    first = make_record(pid=501, create_time=100.0)
    replacement = make_record(pid=501, create_time=200.0, name="replacement.exe")
    snapshots = [[first], [replacement]]
    def loader():
        return snapshots.pop(0) if snapshots else [replacement]
    screen = ProcessesScreen(process_loader=loader, process_verifier=FakeVerifier())
    qtbot.addWidget(screen)
    qtbot.waitUntil(lambda: screen.model.rowCount() == 1 and "Updated" in screen.status_label.text(), timeout=3000)
    screen.table.selectRow(0)
    assert screen.selected_identity == first.identity
    screen.refresh()
    qtbot.waitUntil(lambda: screen.selected_identity is None, timeout=3000)
    assert "Selection cleared" in screen.verification_label.text()


def test_loader_emits_incremental_batches(qtbot):
    records = [make_record(pid=700 + i, name="batch-{}.exe".format(i)) for i in range(5)]
    thread = ProcessLoadThread(loader=lambda: iter(records), classifier=classifier, batch_size=2)
    sizes = []
    thread.batch_ready.connect(lambda batch: sizes.append(len(batch)))
    with qtbot.waitSignal(thread.completed, timeout=3000):
        thread.start()
    thread.wait()
    assert sizes == [2, 2, 1]
