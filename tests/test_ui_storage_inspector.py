"""Tests for metadata and signature inspection in the Storage Explorer."""

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from panther.services.file_inspector import FileInspector
from panther.ui.explorer import ExplorerWidget
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


def _wait_listing(qtbot, widget, timeout=4000):
    qtbot.waitUntil(
        lambda: not widget.is_loading and widget._thread is None,
        timeout=timeout,
    )


def _wait_inspection(qtbot, widget, timeout=5000):
    qtbot.waitUntil(
        lambda: not widget.is_inspecting
        and widget._inspect_thread is None,
        timeout=timeout,
    )


def _row_for(table, name):
    for row in range(table.rowCount()):
        if table.item(row, 0).text() == name:
            return row
    raise AssertionError(f"{name!r} not found in table")


def _select(qtbot, widget, name):
    row = _row_for(widget.table, name)
    widget.table.selectRow(row)
    _wait_inspection(qtbot, widget)
    return row


class SlowInspector(FileInspector):
    def __init__(self, slow_path, delay=0.3):
        super().__init__()
        self.slow_path = os.path.abspath(str(slow_path))
        self.delay = delay

    def inspect(self, path, cancel_event=None):
        if os.path.abspath(str(path)) == self.slow_path:
            time.sleep(self.delay)
        return super().inspect(path, cancel_event=cancel_event)


class FailingInspector(FileInspector):
    def inspect(self, path, cancel_event=None):
        result = super().inspect(path, cancel_event=cancel_event)
        result["metadata"]["ok"] = False
        result["metadata"]["error"] = "denied by test"
        result["metadata"]["error_kind"] = "permission"
        result["signature"]["status"] = "unreadable"
        result["signature"]["ok"] = False
        result["signature"]["error"] = "denied by test"
        result["signature"]["error_kind"] = "permission"
        return result


def test_selecting_file_shows_metadata_and_signature(qtbot, tmp_path):
    _app()
    target = _write(
        tmp_path / "report.pdf", b"%PDF-1.7\n" + b"\x00" * 20
    )

    explorer = ExplorerWidget(initial_path=str(tmp_path))
    qtbot.addWidget(explorer)
    _wait_listing(qtbot, explorer)

    explorer.table.selectRow(_row_for(explorer.table, "report.pdf"))
    _wait_inspection(qtbot, explorer)

    assert explorer.detail_name_label.text() == "report.pdf"
    assert explorer.detail_path_label.text() == str(target)
    assert explorer.detail_extension_label.text() == ".pdf"
    assert explorer.detail_size_label.text() == str(target.stat().st_size) + " B"
    assert "PDF" in explorer.detail_classification_label.text()
    assert explorer.detail_created_label.text() != "—"
    assert explorer.detail_modified_label.text() != "—"
    assert explorer.detail_accessed_label.text() != "—"
    assert explorer.detail_readonly_label.text() in ("Yes", "No")
    assert explorer.detail_attributes_label.text() != "—"
    assert "PDF" in explorer.detail_signature_format_label.text()
    assert "recognized" in (
        explorer.detail_signature_status_label.text().lower()
    )
    match_text = explorer.detail_signature_match_label.text().lower()
    assert "match" in match_text
    assert "does not match" not in match_text
    assert explorer.is_inspecting is False


def test_directory_shows_directory_metadata(qtbot, tmp_path):
    _app()
    folder = tmp_path / "folder"
    folder.mkdir()

    explorer = ExplorerWidget(initial_path=str(tmp_path))
    qtbot.addWidget(explorer)
    _wait_listing(qtbot, explorer)
    _select(qtbot, explorer, "folder")

    assert explorer.detail_type_label.text() == "Folder"
    assert explorer.detail_classification_label.text() == "Folder"
    assert explorer.detail_size_label.text() == "—"
    assert explorer.detail_modified_label.text() != "—"
    assert explorer.detail_accessed_label.text() != "—"
    assert "not applicable" in (
        explorer.detail_signature_format_label.text().lower()
    )
    assert "unsupported" in (
        explorer.detail_signature_status_label.text().lower()
    )


def test_signature_mismatch_is_displayed_informationally(qtbot, tmp_path):
    _app()
    _write(
        tmp_path / "disguised.txt",
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 12,
    )

    explorer = ExplorerWidget(initial_path=str(tmp_path))
    qtbot.addWidget(explorer)
    _wait_listing(qtbot, explorer)
    _select(qtbot, explorer, "disguised.txt")

    assert "PNG" in explorer.detail_signature_format_label.text()
    assert "does not match" in (
        explorer.detail_signature_match_label.text().lower()
    )
    assert "malicious" not in (
        explorer.detail_signature_status_label.text().lower()
    )


def test_loading_state_is_displayed(qtbot, tmp_path):
    _app()
    target = _write(tmp_path / "slow.pdf", b"%PDF-1.7")
    inspector = SlowInspector(target, delay=0.35)

    explorer = ExplorerWidget(
        initial_path=str(tmp_path), inspector=inspector
    )
    qtbot.addWidget(explorer)
    _wait_listing(qtbot, explorer)

    explorer.table.selectRow(_row_for(explorer.table, "slow.pdf"))

    assert explorer.is_inspecting is True
    assert "inspecting" in explorer.detail_inspection_label.text().lower()

    _wait_inspection(qtbot, explorer)
    assert explorer.is_inspecting is False
    assert "inspecting" not in (
        explorer.detail_inspection_label.text().lower()
    )


def test_error_state_is_displayed(qtbot, tmp_path):
    _app()
    _write(tmp_path / "blocked.pdf", b"%PDF-1.7")
    inspector = FailingInspector()

    explorer = ExplorerWidget(
        initial_path=str(tmp_path), inspector=inspector
    )
    qtbot.addWidget(explorer)
    _wait_listing(qtbot, explorer)
    _select(qtbot, explorer, "blocked.pdf")

    assert "denied" in explorer.detail_inspection_label.text().lower()
    assert "not available" in explorer.detail_created_label.text().lower()
    status = explorer.detail_signature_status_label.text().lower()
    assert "unreadable" in status or "denied" in status


def test_rapid_selection_discards_stale_inspection_results(
    qtbot, tmp_path
):
    _app()
    slow = _write(tmp_path / "slow.pdf", b"%PDF-1.7")
    fast = _write(
        tmp_path / "fast.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    )
    inspector = SlowInspector(slow, delay=0.35)

    explorer = ExplorerWidget(
        initial_path=str(tmp_path), inspector=inspector
    )
    qtbot.addWidget(explorer)
    _wait_listing(qtbot, explorer)

    explorer.table.selectRow(_row_for(explorer.table, "slow.pdf"))
    explorer.table.selectRow(_row_for(explorer.table, "fast.png"))
    _wait_inspection(qtbot, explorer, timeout=6000)

    assert explorer.detail_name_label.text() == "fast.png"
    assert explorer.detail_path_label.text() == str(fast)
    assert "PNG" in explorer.detail_signature_format_label.text()

    qtbot.wait(400)
    assert explorer.detail_name_label.text() == "fast.png"
    assert "PNG" in explorer.detail_signature_format_label.text()


def test_link_entry_is_not_inspected(qtbot, tmp_path):
    _app()
    outside = _write(tmp_path / "outside" / "secret.pdf", b"%PDF-1.7")
    link = tmp_path / "link.pdf"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not available: {exc}")

    explorer = ExplorerWidget(initial_path=str(tmp_path))
    qtbot.addWidget(explorer)
    _wait_listing(qtbot, explorer)

    explorer.table.selectRow(_row_for(explorer.table, "link.pdf"))

    assert explorer.is_inspecting is False
    assert explorer._inspect_thread is None
    assert "not inspected" in (
        explorer.detail_inspection_label.text().lower()
    )
    assert "not inspected" in (
        explorer.detail_signature_status_label.text().lower()
    )


def test_inspection_never_changes_scan_roots_or_cleanup(qtbot, tmp_path):
    _app()
    _write(tmp_path / "file.pdf", b"%PDF-1.7")
    screen = StorageScreen()
    qtbot.addWidget(screen)
    panel = screen.explorer_panel
    _wait_listing(qtbot, panel)
    before = dict(screen._scan_roots)

    panel.navigate_to(str(tmp_path))
    _wait_listing(qtbot, panel)
    _select(qtbot, panel, "file.pdf")

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
        assert "open" not in text


def test_storage_destruction_with_active_inspection_is_clean(tmp_path):
    target = _write(tmp_path / "file.pdf", b"%PDF-1.7\n" + b"x" * 20)
    script = f"""
        import os
        import time
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from panther.services.file_inspector import FileInspector
        from panther.ui.explorer import ExplorerWidget

        app = QApplication([])
        original = FileInspector.inspect
        def slow(self, path, cancel_event=None):
            time.sleep(0.4)
            return original(self, path, cancel_event=cancel_event)
        FileInspector.inspect = slow
        widget = ExplorerWidget(initial_path={str(tmp_path)!r})
        entry = {{
            "name": "file.pdf",
            "path": {str(target)!r},
            "type": "file",
            "size": {target.stat().st_size},
            "modified": "",
        }}
        QTimer.singleShot(150, lambda: widget._start_inspection(entry))
        QTimer.singleShot(350, widget.deleteLater)
        QTimer.singleShot(1000, app.quit)
        app.exec()
        print("inspector-destroy-ok")
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
    assert "inspector-destroy-ok" in result.stdout
