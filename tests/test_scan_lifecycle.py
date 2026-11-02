"""Lifecycle regressions for Storage background scanning."""

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from PySide6.QtCore import QThread

from panther.services.file_scanner import FileScanner
from panther.ui.scan_controller import ScanController
from panther.ui.storage import StorageScreen


def _write_tree(root: Path, count=8):
    root.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        (root / f"{index}.txt").write_text(f"file {index}")


def _subprocess_env():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["QT_QPA_PLATFORM"] = "offscreen"
    return env


def _run_script(script):
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_actual_controller_to_storage_delivery(qtbot, tmp_path):
    _write_tree(tmp_path)
    screen = StorageScreen()
    qtbot.addWidget(screen)

    with qtbot.waitSignal(screen.scan_controller.finished, timeout=5000):
        assert screen.scan_controller.start("largest", str(tmp_path), 2)

    qtbot.waitUntil(lambda: not screen.scan_controller.is_running, timeout=3000)
    assert screen.largest_files_data
    assert screen.scan_largest_btn.isEnabled()
    assert QThread.currentThread() is screen.thread()
    screen.scan_controller.shutdown()


def test_finished_result_does_not_reenable_controls_early(qtbot):
    screen = StorageScreen()
    qtbot.addWidget(screen)
    screen._on_scan_started("largest")

    screen._on_scan_finished(
        {
            "generation": 1,
            "kind": "largest",
            "files": [],
            "largest": [],
            "duplicates": [],
            "errors": [],
            "partial": False,
            "files_scanned": 0,
            "directories_scanned": 0,
            "bytes_scanned": 0,
            "elapsed_seconds": 0.0,
        }
    )
    assert screen.scan_largest_btn.isEnabled() is False

    screen._on_scan_state_changed(False)
    assert screen.scan_largest_btn.isEnabled() is True


def test_shutdown_timeout_is_bounded_and_keeps_thread_safe(
    qtbot, tmp_path, monkeypatch
):
    _write_tree(tmp_path, count=20)
    original = FileScanner._scan_file

    def slow_scan_file(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        time.sleep(0.2)
        return result

    monkeypatch.setattr(FileScanner, "_scan_file", slow_scan_file)
    controller = ScanController()
    with qtbot.waitSignal(controller.progress, timeout=2000):
        assert controller.start("largest", str(tmp_path), 1)
    started = time.monotonic()
    result = controller.shutdown(timeout_ms=50)
    elapsed = time.monotonic() - started

    assert result is False
    assert elapsed < 0.5
    assert controller.is_running is True

    qtbot.waitUntil(lambda: not controller.is_running, timeout=5000)
    controller.shutdown()


def test_active_screen_destruction_subprocess_exit_is_clean(tmp_path):
    _write_tree(tmp_path, count=30)
    script = f"""
        import time
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from panther.services.file_scanner import FileScanner
        from panther.ui.storage import StorageScreen

        app = QApplication([])
        screen = StorageScreen()
        original = FileScanner._scan_file
        def slow(self, *args, **kwargs):
            time.sleep(0.01)
            return original(self, *args, **kwargs)
        FileScanner._scan_file = slow
        screen.scan_controller.start("largest", {str(tmp_path)!r}, 2)
        screen.deleteLater()
        QTimer.singleShot(1000, app.quit)
        app.exec()
        print("destroy-ok")
    """
    result = _run_script(script)
    assert result.returncode == 0, result.stderr
    assert "destroy-ok" in result.stdout


def test_subprocess_repeated_worker_lifecycle_exits_cleanly(tmp_path):
    _write_tree(tmp_path)
    script = f"""
        from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
        from panther.ui.scan_controller import ScanController

        app = QCoreApplication([])
        root = {str(tmp_path)!r}
        for index in range(20):
            controller = ScanController()
            loop = QEventLoop()
            def done(*args):
                loop.quit()
            controller.finished.connect(done)
            controller.cancelled.connect(done)
            controller.failed.connect(done)
            assert controller.start("largest", root, 2)
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            assert controller.shutdown(1000)
        print("stress-ok")
    """
    result = _run_script(script)
    assert result.returncode == 0, result.stderr
    assert "stress-ok" in result.stdout
