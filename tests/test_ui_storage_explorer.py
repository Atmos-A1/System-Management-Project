"""Tests for the read-only Storage Explorer UI."""

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from panther.services.directory_browser import DirectoryBrowser
from panther.ui.explorer import ExplorerWidget
from panther.ui.storage import StorageScreen


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _wait_idle(qtbot, widget, timeout=3000):
    qtbot.waitUntil(
        lambda: not widget.is_loading and widget._thread is None,
        timeout=timeout,
    )


def _row_for(table, name):
    for row in range(table.rowCount()):
        if table.item(row, 0).text() == name:
            return row
    raise AssertionError(f"{name!r} not found in table")


class SlowBrowser(DirectoryBrowser):
    def __init__(self, slow_path, delay=0.2):
        super().__init__()
        self.slow_path = os.path.abspath(str(slow_path))
        self.delay = delay

    def list_directory(self, path, limit=None, cancel_event=None):
        if os.path.abspath(str(path)) == self.slow_path:
            time.sleep(self.delay)
        return super().list_directory(
            path, limit=limit, cancel_event=cancel_event
        )


def test_explorer_tab_is_in_correct_position(qtbot):
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
    assert isinstance(screen.explorer_panel, ExplorerWidget)
    assert "read-only" in (
        screen.explorer_panel.read_only_label.text().lower()
    )
    _wait_idle(qtbot, screen.explorer_panel)


def test_initial_listing_and_directory_navigation(qtbot, tmp_path):
    _app()
    root = tmp_path / "root"
    sub = root / "sub"
    sub.mkdir(parents=True)
    (root / "root.txt").write_text("root")
    (sub / "child.txt").write_text("child")

    explorer = ExplorerWidget(initial_path=str(root))
    qtbot.addWidget(explorer)
    _wait_idle(qtbot, explorer)

    assert explorer.current_path == str(root)
    assert explorer.table.rowCount() == 2

    explorer.navigate_to(str(sub))
    _wait_idle(qtbot, explorer)

    assert explorer.current_path == str(sub)
    assert explorer.table.rowCount() == 1
    assert explorer.table.item(0, 0).text() == "child.txt"
    assert explorer.back_button.isEnabled() is True


def test_back_forward_up_and_refresh_navigation(qtbot, tmp_path):
    _app()
    root = tmp_path / "root"
    sub = root / "sub"
    sub.mkdir(parents=True)
    (sub / "child.txt").write_text("child")

    explorer = ExplorerWidget(initial_path=str(root))
    qtbot.addWidget(explorer)
    _wait_idle(qtbot, explorer)

    explorer.navigate_to(str(sub))
    _wait_idle(qtbot, explorer)
    explorer.back_button.click()
    _wait_idle(qtbot, explorer)
    assert explorer.current_path == str(root)

    explorer.forward_button.click()
    _wait_idle(qtbot, explorer)
    assert explorer.current_path == str(sub)

    explorer.up_button.click()
    _wait_idle(qtbot, explorer)
    assert explorer.current_path == str(root)

    (root / "new.txt").write_text("new")
    explorer.refresh_button.click()
    _wait_idle(qtbot, explorer)
    assert _row_for(explorer.table, "new.txt") >= 0


def test_selecting_a_row_updates_details(qtbot, tmp_path):
    _app()
    target = tmp_path / "report.txt"
    target.write_text("hello")

    explorer = ExplorerWidget(initial_path=str(tmp_path))
    qtbot.addWidget(explorer)
    _wait_idle(qtbot, explorer)

    explorer.table.selectRow(_row_for(explorer.table, "report.txt"))

    assert explorer.detail_name_label.text() == "report.txt"
    assert explorer.detail_path_label.text() == str(target)
    assert explorer.detail_type_label.text() == "File"
    assert explorer.detail_size_label.text() == "5 B"
    assert explorer.detail_link_label.text() == "No"
    assert explorer.detail_hidden_label.text() == "No"


def test_link_entry_is_not_followed(qtbot, tmp_path):
    _app()
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    link = root / "outside-link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not available: {exc}")

    explorer = ExplorerWidget(initial_path=str(root))
    qtbot.addWidget(explorer)
    _wait_idle(qtbot, explorer)

    row = _row_for(explorer.table, "outside-link")
    explorer.table.selectRow(row)
    assert explorer.detail_link_label.text() == "Link"

    explorer._on_double_clicked(explorer.table.item(row, 0))
    _wait_idle(qtbot, explorer)

    assert explorer.current_path == str(root)
    assert explorer.table.rowCount() == 1
    assert "not followed" in explorer.status_label.text().lower()
    assert _row_for(explorer.table, "outside-link") == 0


def test_invalid_path_keeps_last_valid_location(qtbot, tmp_path):
    _app()
    root = tmp_path / "root"
    root.mkdir()
    (root / "visible.txt").write_text("x")
    missing = tmp_path / "missing"

    explorer = ExplorerWidget(initial_path=str(root))
    qtbot.addWidget(explorer)
    _wait_idle(qtbot, explorer)

    explorer.navigate_to(str(missing))
    _wait_idle(qtbot, explorer)

    assert explorer.current_path == str(root)
    assert explorer.path_input.text() == str(root)
    assert explorer.table.rowCount() == 1
    assert explorer.table.item(0, 0).text() == "visible.txt"
    assert "cannot open" in explorer.status_label.text().lower()


def test_rapid_navigation_discards_stale_results(qtbot, tmp_path):
    _app()
    root = tmp_path / "root"
    slow = root / "slow"
    fast = root / "fast"
    slow.mkdir(parents=True)
    fast.mkdir()
    (root / "root.txt").write_text("root")
    (slow / "slow.txt").write_text("slow")
    (fast / "fast.txt").write_text("fast")
    browser = SlowBrowser(slow, delay=0.2)

    explorer = ExplorerWidget(initial_path=str(root), browser=browser)
    qtbot.addWidget(explorer)
    _wait_idle(qtbot, explorer)

    explorer.navigate_to(str(slow))
    explorer.navigate_to(str(fast))
    _wait_idle(qtbot, explorer, timeout=5000)

    assert explorer.current_path == str(fast)
    assert explorer.table.item(0, 0).text() == "fast.txt"
    qtbot.wait(250)
    assert explorer.current_path == str(fast)
    assert explorer.table.item(0, 0).text() == "fast.txt"


def test_loading_and_completion_states(qtbot, tmp_path):
    _app()
    root = tmp_path / "root"
    slow = root / "slow"
    slow.mkdir(parents=True)
    browser = SlowBrowser(slow, delay=0.2)

    explorer = ExplorerWidget(initial_path=str(root), browser=browser)
    qtbot.addWidget(explorer)
    _wait_idle(qtbot, explorer)

    explorer.navigate_to(str(slow))
    assert explorer.is_loading is True
    assert explorer.progress_bar.isHidden() is False
    assert "loading" in explorer.status_label.text().lower()

    _wait_idle(qtbot, explorer)
    assert explorer.is_loading is False
    assert explorer.progress_bar.isHidden() is True
    assert "entries" in explorer.status_label.text().lower()


def test_explorer_has_no_cleanup_controls(qtbot, tmp_path):
    _app()
    explorer = ExplorerWidget(initial_path=str(tmp_path))
    qtbot.addWidget(explorer)
    _wait_idle(qtbot, explorer)

    texts = [
        button.text().casefold()
        for button in explorer.findChildren(QPushButton)
    ]
    for text in texts:
        assert "recycle" not in text
        assert "delete" not in text
        assert "cleanup" not in text
        assert "move" not in text


def test_explorer_navigation_never_changes_scan_roots_or_cleanup(
    qtbot, tmp_path
):
    _app()
    screen = StorageScreen()
    qtbot.addWidget(screen)
    panel = screen.explorer_panel
    _wait_idle(qtbot, panel)
    before = dict(screen._scan_roots)

    (tmp_path / "visible.txt").write_text("x")
    panel.navigate_to(str(tmp_path))
    _wait_idle(qtbot, panel)

    assert screen._scan_roots == before
    assert screen.delete_largest_btn.isEnabled() is False
    assert screen.remove_dups_btn.isEnabled() is False

    panel.table.selectRow(_row_for(panel.table, "visible.txt"))
    assert screen._scan_roots == before
    assert screen.delete_largest_btn.isEnabled() is False
    assert screen.remove_dups_btn.isEnabled() is False


def test_explorer_shutdown_is_bounded_and_safe(qtbot, tmp_path):
    _app()
    root = tmp_path / "root"
    slow = root / "slow"
    slow.mkdir(parents=True)
    browser = SlowBrowser(slow, delay=0.3)

    explorer = ExplorerWidget(initial_path=str(root), browser=browser)
    qtbot.addWidget(explorer)
    _wait_idle(qtbot, explorer)

    explorer.navigate_to(str(slow))
    started = time.monotonic()
    result = explorer.shutdown(timeout_ms=50)
    elapsed = time.monotonic() - started

    assert result is False
    assert elapsed < 0.5
    assert explorer._thread is not None

    qtbot.waitUntil(lambda: explorer._thread is None, timeout=5000)
    assert explorer.shutdown() is True


def test_storage_destruction_with_active_explorer_listing_is_clean(tmp_path):
    script = f"""
        import time
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from panther.services.directory_browser import DirectoryBrowser
        from panther.ui.storage import StorageScreen

        app = QApplication([])
        original = DirectoryBrowser.list_directory
        def slow(self, path, limit=None, cancel_event=None):
            time.sleep(0.2)
            return original(self, path, limit=limit, cancel_event=cancel_event)
        DirectoryBrowser.list_directory = slow
        screen = StorageScreen()
        screen.deleteLater()
        QTimer.singleShot(700, app.quit)
        app.exec()
        print("explorer-destroy-ok")
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
    assert "explorer-destroy-ok" in result.stdout
