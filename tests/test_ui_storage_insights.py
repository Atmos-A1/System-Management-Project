"""Tests for the Storage Insights UI."""

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication, QPushButton

from panther.services import storage_analysis as analysis_module
from panther.services.storage_analysis import StorageAnalysis
from panther.ui.insights import InsightsWidget
from panther.ui.storage import StorageScreen


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _write(path, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _wait_idle(qtbot, widget, timeout=5000):
    qtbot.waitUntil(
        lambda: not widget.is_running and widget._thread is None,
        timeout=timeout,
    )


def _wait_explorer_idle(qtbot, widget, timeout=5000):
    qtbot.waitUntil(
        lambda: not widget.is_loading and widget._thread is None,
        timeout=timeout,
    )


def _row_for(table, name, column=0):
    for row in range(table.rowCount()):
        if table.item(row, column).text() == name:
            return row
    raise AssertionError(f"{name!r} not found")


class SlowAnalysis(StorageAnalysis):
    def __init__(self, slow_path, delay=0.25):
        super().__init__()
        self.slow_path = os.path.abspath(str(slow_path))
        self.delay = delay

    def analyze(self, roots, cancel_event=None, progress_callback=None):
        if any(
            os.path.abspath(str(root)) == self.slow_path for root in roots
        ):
            if progress_callback is not None:
                progress_callback(
                    {
                        "files_scanned": 0,
                        "directories_scanned": 0,
                        "bytes_scanned": 0,
                        "current_path": self.slow_path,
                        "elapsed_seconds": 0.0,
                    }
                )
            time.sleep(self.delay)
        return super().analyze(
            roots,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
        )


def test_insights_tab_is_in_correct_position(qtbot):
    _app()
    screen = StorageScreen()
    qtbot.addWidget(screen)

    assert screen.tabs.count() == 6
    assert [screen.tabs.tabText(i) for i in range(6)] == [
        "Overview",
        "Largest Files",
        "Duplicates",
        "Explorer",
        "Insights",
        "Scan History",
    ]
    assert isinstance(screen.insights_panel, InsightsWidget)
    assert "never authorize cleanup" in (
        screen.insights_panel.read_only_label.text().lower()
    )
    _wait_explorer_idle(qtbot, screen.explorer_panel)


def test_insights_has_folder_and_file_type_views(qtbot):
    _app()
    panel = InsightsWidget(initial_path=str(Path.home()))
    qtbot.addWidget(panel)

    assert panel.analysis_tabs.count() == 2
    assert panel.analysis_tabs.tabText(0) == "Folder Sizes"
    assert panel.analysis_tabs.tabText(1) == "File Types"


def test_analysis_completes_and_populates_both_views(qtbot, tmp_path):
    _app()
    _write(tmp_path / "alpha" / "a.bin", b"123")
    _write(tmp_path / "alpha" / "nested" / "b.bin", b"12345")
    _write(tmp_path / "root.txt", b"12")
    panel = InsightsWidget(initial_path=str(tmp_path))
    qtbot.addWidget(panel)

    panel.start_analysis()
    _wait_idle(qtbot, panel)

    assert panel.current_result["status"] == "complete"
    assert panel.folder_table.rowCount() == 1
    alpha_row = _row_for(panel.folder_table, "alpha")
    assert panel.folder_table.item(alpha_row, 2).text() == "8 B"
    assert panel.folder_table.item(alpha_row, 4).text() == "Complete"
    assert panel.file_type_table.rowCount() == 2
    assert _row_for(panel.file_type_table, ".bin") >= 0
    assert "complete" in panel.status_label.text().lower()
    assert "10" in panel.summary_label.text()


def test_progress_is_displayed_while_analysis_runs(qtbot, tmp_path):
    _app()
    slow = tmp_path / "slow"
    slow.mkdir()
    _write(slow / "file.bin", b"1")
    panel = InsightsWidget(
        initial_path=str(slow), service=SlowAnalysis(slow, delay=0.25)
    )
    qtbot.addWidget(panel)

    panel.start_analysis()

    assert panel.is_running is True
    assert panel.progress_bar.isHidden() is False
    assert "analyzing" in panel.status_label.text().lower()
    assert panel.analyze_button.isEnabled() is False

    _wait_idle(qtbot, panel)
    assert panel.progress_bar.isHidden() is True
    assert panel.analyze_button.isEnabled() is True


def test_cancellation_shows_cancelled_state(qtbot, tmp_path):
    _app()
    slow = tmp_path / "slow"
    slow.mkdir()
    _write(slow / "file.bin", b"1")
    panel = InsightsWidget(
        initial_path=str(slow), service=SlowAnalysis(slow, delay=0.35)
    )
    qtbot.addWidget(panel)

    panel.start_analysis()
    panel.cancel_analysis()
    _wait_idle(qtbot, panel)

    assert panel.current_result["status"] == "cancelled"
    assert "cancelled" in panel.status_label.text().lower()
    assert panel.progress_bar.isHidden() is True


def test_empty_result_is_reported(qtbot, tmp_path):
    _app()
    panel = InsightsWidget(initial_path=str(tmp_path))
    qtbot.addWidget(panel)

    panel.start_analysis()
    _wait_idle(qtbot, panel)

    assert panel.current_result["status"] == "complete"
    assert panel.folder_table.rowCount() == 0
    assert panel.file_type_table.rowCount() == 0
    assert "no files" in panel.status_label.text().lower()


def test_failed_analysis_is_reported(qtbot, tmp_path):
    _app()
    missing = tmp_path / "missing"
    panel = InsightsWidget(initial_path=str(missing))
    qtbot.addWidget(panel)

    panel.start_analysis()
    _wait_idle(qtbot, panel)

    assert panel.current_result["status"] == "failed"
    assert "failed" in panel.status_label.text().lower()
    assert panel.folder_table.rowCount() == 0
    assert panel.file_type_table.rowCount() == 0


def test_partial_analysis_is_clearly_communicated(
    qtbot, tmp_path, monkeypatch
):
    _app()
    _write(tmp_path / "good" / "a.bin", b"123")
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    _write(blocked / "hidden.bin", b"123456")
    real_scandir = os.scandir

    def fake_scandir(path):
        if os.fspath(path) == str(blocked):
            raise PermissionError("denied by test")
        return real_scandir(path)

    monkeypatch.setattr(analysis_module.os, "scandir", fake_scandir)
    panel = InsightsWidget(initial_path=str(tmp_path))
    qtbot.addWidget(panel)

    panel.start_analysis()
    _wait_idle(qtbot, panel)

    assert panel.current_result["status"] == "partial"
    assert "partial" in panel.status_label.text().lower()
    assert "1" in panel.summary_label.text()
    blocked_row = _row_for(panel.folder_table, "blocked")
    assert panel.folder_table.item(blocked_row, 4).text() == "Partial"


def test_folder_selection_opens_existing_explorer(qtbot, tmp_path):
    _app()
    folder = tmp_path / "folder"
    _write(folder / "file.txt", b"1")
    screen = StorageScreen()
    qtbot.addWidget(screen)
    panel = screen.insights_panel

    panel.start_analysis(str(tmp_path))
    _wait_idle(qtbot, panel)
    row = _row_for(panel.folder_table, "folder")
    panel.folder_table.selectRow(row)
    assert panel.open_folder_button.isEnabled() is True
    panel.open_folder_button.click()

    assert screen.tabs.currentIndex() == 3
    _wait_explorer_idle(qtbot, screen.explorer_panel)
    assert screen.explorer_panel.current_path == str(folder)


def test_rapid_analysis_requests_do_not_show_stale_results(
    qtbot, tmp_path
):
    _app()
    slow = tmp_path / "slow"
    fast = tmp_path / "fast"
    slow.mkdir()
    fast.mkdir()
    _write(slow / "slow-folder" / "slow.bin", b"1")
    _write(fast / "fast-folder" / "fast.bin", b"1")
    panel = InsightsWidget(
        initial_path=str(slow), service=SlowAnalysis(slow, delay=0.3)
    )
    qtbot.addWidget(panel)

    panel.start_analysis(str(slow))
    panel.start_analysis(str(fast))
    _wait_idle(qtbot, panel, timeout=6000)

    assert panel.current_result["roots"] == [str(fast)]
    assert _row_for(panel.folder_table, "fast-folder") >= 0
    qtbot.wait(300)
    assert panel.current_result["roots"] == [str(fast)]


def test_insights_never_changes_scan_roots_or_cleanup(qtbot, tmp_path):
    _app()
    _write(tmp_path / "file.bin", b"1")
    screen = StorageScreen()
    qtbot.addWidget(screen)
    panel = screen.insights_panel
    before = dict(screen._scan_roots)

    panel.start_analysis(str(tmp_path))
    _wait_idle(qtbot, panel)

    assert screen._scan_roots == before
    assert screen.delete_largest_btn.isEnabled() is False
    assert screen.remove_dups_btn.isEnabled() is False

    texts = [
        button.text().casefold()
        for button in panel.findChildren(QPushButton)
    ]
    for text in texts:
        assert "recycle" not in text
        assert "delete" not in text
        assert "cleanup" not in text
        assert "move" not in text


def test_insights_shutdown_is_bounded_and_safe(qtbot, tmp_path):
    _app()
    slow = tmp_path / "slow"
    slow.mkdir()
    _write(slow / "file.bin", b"1")
    panel = InsightsWidget(
        initial_path=str(slow), service=SlowAnalysis(slow, delay=0.4)
    )
    qtbot.addWidget(panel)

    panel.start_analysis()
    started = time.monotonic()
    result = panel.shutdown(timeout_ms=50)
    elapsed = time.monotonic() - started

    assert result is False
    assert elapsed < 0.5
    assert panel._thread is not None

    qtbot.waitUntil(lambda: panel._thread is None, timeout=5000)
    assert panel.shutdown() is True


def test_storage_destruction_with_active_analysis_is_clean(tmp_path):
    script = f"""
        import time
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from panther.services.storage_analysis import StorageAnalysis
        from panther.ui.storage import StorageScreen

        app = QApplication([])
        original = StorageAnalysis.analyze
        def slow(self, roots, cancel_event=None, progress_callback=None):
            time.sleep(0.3)
            return original(
                self, roots, cancel_event=cancel_event,
                progress_callback=progress_callback,
            )
        StorageAnalysis.analyze = slow
        screen = StorageScreen()
        screen.insights_panel.start_analysis({str(tmp_path)!r})
        screen.deleteLater()
        QTimer.singleShot(900, app.quit)
        app.exec()
        print("insights-destroy-ok")
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = str(
        Path(__file__).resolve().parents[1] / "src"
    )
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "insights-destroy-ok" in result.stdout
