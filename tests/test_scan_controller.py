"""Tests for the background Storage scan controller."""

import threading
import time

from PySide6.QtTest import QSignalSpy

from panther.services.file_scanner import FileScanner
from panther.ui.scan_controller import ScanController


def _write(path, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_scan_runs_on_a_worker_thread_and_emits_progress(
    qtbot, tmp_path, monkeypatch
):
    _write(tmp_path / "a.txt", b"123")
    _write(tmp_path / "sub" / "b.txt", b"4567")
    worker_threads = []
    original = FileScanner.scan_directory

    def wrapped(self, *args, **kwargs):
        worker_threads.append(threading.current_thread())
        return original(self, *args, **kwargs)

    monkeypatch.setattr(FileScanner, "scan_directory", wrapped)

    controller = ScanController()
    progress = []
    controller.progress.connect(progress.append)

    with qtbot.waitSignal(controller.finished, timeout=5000) as blocker:
        assert controller.start("largest", str(tmp_path), max_depth=2)

    payload = blocker.args[0]
    assert payload["kind"] == "largest"
    assert payload["generation"] == 1
    assert {item["name"] for item in payload["largest"]} == {
        "a.txt",
        "b.txt",
    }
    assert worker_threads and worker_threads[0] is not threading.main_thread()
    assert progress
    assert any(
        item["phase"] == "scan" and item["files_scanned"] >= 1
        for item in progress
    )
    qtbot.waitUntil(lambda: not controller.is_running, timeout=2000)
    controller.shutdown()


def test_duplicate_scan_hashes_on_worker_and_reports_hash_progress(
    qtbot, tmp_path
):
    _write(tmp_path / "a.txt", b"same")
    _write(tmp_path / "b.txt", b"same")
    controller = ScanController()
    progress = []
    controller.progress.connect(progress.append)

    with qtbot.waitSignal(controller.finished, timeout=5000) as blocker:
        assert controller.start("duplicates", str(tmp_path), max_depth=2)

    payload = blocker.args[0]
    assert payload["kind"] == "duplicates"
    assert payload["duplicates"][0]["count"] == 2
    assert any(item["phase"] == "hash" for item in progress)
    qtbot.waitUntil(lambda: not controller.is_running, timeout=2000)
    controller.shutdown()


def test_progress_cancellation_stops_scan_without_finished_result(
    qtbot, tmp_path, monkeypatch
):
    for index in range(40):
        _write(tmp_path / f"{index}.txt", b"x")

    original_scan_file = FileScanner._scan_file

    def slow_scan_file(self, *args, **kwargs):
        time.sleep(0.005)
        return original_scan_file(self, *args, **kwargs)

    monkeypatch.setattr(FileScanner, "_scan_file", slow_scan_file)

    controller = ScanController()
    finished_spy = QSignalSpy(controller.finished)

    def cancel_after_first_progress(item):
        if item["phase"] == "scan" and item["files_scanned"] >= 1:
            controller.cancel()

    controller.progress.connect(cancel_after_first_progress)

    with qtbot.waitSignal(controller.cancelled, timeout=5000) as blocker:
        assert controller.start("largest", str(tmp_path), max_depth=2)

    assert blocker.args[0]["kind"] == "largest"
    assert finished_spy.count() == 0
    qtbot.waitUntil(lambda: not controller.is_running, timeout=2000)
    controller.shutdown()


def test_worker_exception_is_reported_as_failure(qtbot, tmp_path, monkeypatch):
    controller = ScanController()

    def fail_scan(self, *args, **kwargs):
        raise RuntimeError("scanner exploded")

    monkeypatch.setattr(FileScanner, "scan_directory", fail_scan)

    with qtbot.waitSignal(controller.failed, timeout=5000) as blocker:
        assert controller.start("largest", str(tmp_path), max_depth=1)

    payload = blocker.args[0]
    assert payload["kind"] == "largest"
    assert "scanner exploded" in payload["error"]
    qtbot.waitUntil(lambda: not controller.is_running, timeout=2000)
    controller.shutdown()


def test_missing_root_finishes_as_partial_scan(qtbot, tmp_path):
    controller = ScanController()

    with qtbot.waitSignal(controller.finished, timeout=5000) as blocker:
        assert controller.start(
            "largest", str(tmp_path / "missing"), max_depth=1
        )

    payload = blocker.args[0]
    assert payload["files_scanned"] == 0
    assert payload["partial"] is True
    assert payload["errors"]
    qtbot.waitUntil(lambda: not controller.is_running, timeout=2000)
    controller.shutdown()


def test_stale_generation_signals_are_ignored(qtbot):
    controller = ScanController()
    finished_spy = QSignalSpy(controller.finished)
    progress_spy = QSignalSpy(controller.progress)

    controller._generation = 2
    controller._handle_finished({"generation": 1, "kind": "largest"})
    controller._handle_progress({"generation": 1, "phase": "scan"})

    assert finished_spy.count() == 0
    assert progress_spy.count() == 0


def test_start_is_rejected_while_a_scan_is_active(qtbot, tmp_path, monkeypatch):
    _write(tmp_path / "a.txt")
    original = FileScanner.scan_directory

    def slow_scan(self, *args, **kwargs):
        time.sleep(0.1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(FileScanner, "scan_directory", slow_scan)
    controller = ScanController()

    assert controller.start("largest", str(tmp_path), max_depth=1)
    assert controller.start("largest", str(tmp_path), max_depth=1) is False
    with qtbot.waitSignal(controller.finished, timeout=5000):
        pass
    qtbot.waitUntil(lambda: not controller.is_running, timeout=2000)
    controller.shutdown()


def test_shutdown_cancels_active_work(qtbot, tmp_path, monkeypatch):
    for index in range(40):
        _write(tmp_path / f"{index}.txt")

    original = FileScanner._scan_file

    def slow_scan_file(self, *args, **kwargs):
        time.sleep(0.01)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(FileScanner, "_scan_file", slow_scan_file)
    controller = ScanController()
    controller.start("largest", str(tmp_path), max_depth=1)
    qtbot.wait(50)

    assert controller.shutdown(timeout_ms=3000) is True
    assert controller.is_running is False
