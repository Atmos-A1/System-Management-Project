"""UI-level tests for Storage background scanning controls."""

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QPushButton,
)

import panther.ui.storage as storage_module
from panther.ui.storage import StorageScreen


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_storage_progress_and_controls_are_wired(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)

    assert widget.cancel_scan_btn.isEnabled() is False
    assert widget.scan_progress_bar.isHidden()

    widget._on_scan_started("largest")
    assert widget.scan_largest_btn.isEnabled() is False
    assert widget.scan_dups_btn.isEnabled() is False
    assert widget.delete_largest_btn.isEnabled() is False
    assert widget.remove_dups_btn.isEnabled() is False
    assert widget.cancel_scan_btn.isEnabled() is True
    assert widget.cancel_scan_btn.isHidden() is False
    assert widget.scan_progress_bar.isHidden() is False

    widget._on_scan_progress(
        {
            "generation": 1,
            "kind": "largest",
            "phase": "scan",
            "files_scanned": 12,
            "directories_scanned": 3,
            "bytes_scanned": 2048,
            "current_path": "/tmp/example/file.txt",
            "elapsed_seconds": 0.5,
        }
    )
    status = widget.scan_status_label.text()
    assert "12" in status
    assert "3" in status
    assert "2.0 KB" in status
    assert "/tmp/example/file.txt" in widget.scan_path_label.text()

    widget._on_scan_finished(
        {
            "generation": 1,
            "kind": "largest",
            "files": [],
            "largest": [],
            "duplicates": [],
            "errors": [],
            "partial": False,
            "files_scanned": 12,
            "directories_scanned": 3,
            "bytes_scanned": 2048,
            "elapsed_seconds": 0.5,
        }
    )
    widget._on_scan_state_changed(False)
    assert widget.scan_largest_btn.isEnabled() is True
    assert widget.cancel_scan_btn.isEnabled() is False
    assert widget.scan_progress_bar.isHidden()


def test_storage_cancelled_and_partial_states_are_visible(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)

    widget._on_scan_started("duplicates")
    widget._on_scan_cancelled({"generation": 1, "kind": "duplicates"})
    widget._on_scan_state_changed(False)
    assert "cancelled" in widget.scan_status_label.text().lower()
    assert widget.scan_dups_btn.isEnabled() is True

    widget._on_scan_finished(
        {
            "generation": 2,
            "kind": "largest",
            "files": [],
            "largest": [],
            "duplicates": [],
            "errors": [{"path": "/x", "error": "denied", "kind": "permission"}],
            "partial": True,
            "files_scanned": 0,
            "directories_scanned": 0,
            "bytes_scanned": 0,
            "elapsed_seconds": 0.1,
        }
    )
    assert "skipped" in widget.scan_status_label.text().lower()


def test_cleanup_outcome_text_lists_each_path(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)

    text = widget._format_cleanup_outcomes(
        {
            "moved": 1,
            "failed": 1,
            "outcomes": [
                {"path": "/a.txt", "status": "moved", "reason": ""},
                {
                    "path": "/b.txt",
                    "status": "rejected",
                    "reason": "Outside approved scan roots",
                },
            ],
        }
    )

    assert "Moved: /a.txt" in text
    assert "Rejected: /b.txt: Outside approved scan roots" in text


def test_scan_result_records_actual_root(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)

    widget._on_scan_finished(
        {
            "generation": 3,
            "kind": "largest",
            "root": "/scanned/root",
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

    assert widget._scan_roots["largest"] == "/scanned/root"


def test_cleanup_passes_only_eligible_paths_and_review_cancel_blocks_action(
    qtbot, monkeypatch
):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)
    widget._scan_roots["largest"] = "/approved/root"
    widget._populate_largest(
        [
            {"path": "/approved/root/a.txt", "size": 10},
            {"path": "/approved/root/b.txt", "size": 20},
        ]
    )
    widget.largest_table.selectRow(0)
    widget.largest_table.selectRow(1)

    preview = {
        "allowed": ["/approved/root/a.txt"],
        "rejected": [
            {
                "path": "/approved/root/b.txt",
                "allowed": False,
                "reason": "Path changed since scan",
            }
        ],
        "decisions": [],
    }
    monkeypatch.setattr(
        storage_module.cleanup_manager,
        "preflight_cleanup",
        lambda paths, roots: preview,
    )
    captured = {}

    def fake_move(paths, allowed_roots=None):
        captured["paths"] = paths
        captured["roots"] = allowed_roots
        return {
            "moved": 1,
            "failed": 0,
            "outcomes": [
                {"path": paths[0], "status": "moved", "reason": ""}
            ],
        }

    monkeypatch.setattr(
        storage_module.cleanup_manager, "move_to_recycle_bin", fake_move
    )

    class FakeReviewDialog:
        def __init__(self, preview_arg, sizes, parent=None):
            self.eligible_paths = preview_arg["allowed"]

        def exec(self):
            return QDialog.DialogCode.Accepted

    class FakeResultDialog:
        def __init__(self, result, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(storage_module, "CleanupReviewDialog", FakeReviewDialog)
    monkeypatch.setattr(storage_module, "CleanupResultDialog", FakeResultDialog)
    monkeypatch.setattr(widget, "scan_largest_files", lambda: None)

    widget.delete_selected_largest()

    assert captured["paths"] == ["/approved/root/a.txt"]
    assert captured["roots"] == ["/approved/root"]

    captured.clear()

    class FakeCancelledDialog(FakeReviewDialog):
        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(
        storage_module, "CleanupReviewDialog", FakeCancelledDialog
    )
    widget.largest_table.selectRow(0)
    widget.largest_table.selectRow(1)
    widget.delete_selected_largest()
    assert captured == {}


def test_duplicate_scan_finish_updates_panel_summary(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)

    widget._on_scan_finished(
        {
            "generation": 4,
            "kind": "duplicates",
            "root": "/scanned/root",
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

    assert "0 duplicate groups" in widget.scan_status_label.text()
    assert widget.dups_panel.group_count == 0


def test_duplicate_cleanup_uses_only_selected_copies(
    qtbot, monkeypatch
):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)
    widget._scan_roots["duplicates"] = "/approved/root"
    widget._populate_duplicates(
        [
            {
                "size": 100,
                "count": 3,
                "potential_savings": 200,
                "files": [
                    {
                        "path": "/approved/root/a.txt",
                        "directory": "/approved/root",
                        "size": 100,
                        "modified": "2024-01-01 00:00:00",
                    },
                    {
                        "path": "/approved/root/b.txt",
                        "directory": "/approved/root",
                        "size": 100,
                        "modified": "2023-01-01 00:00:00",
                    },
                    {
                        "path": "/approved/root/c.txt",
                        "directory": "/approved/root",
                        "size": 100,
                        "modified": "2022-01-01 00:00:00",
                    },
                ],
            }
        ]
    )
    selection = widget.dups_panel.current_selection
    assert selection.removal_count == 0
    assert selection.set_remove("/approved/root/a.txt", True)
    widget.dups_panel.refresh_current_selection()

    preview = {
        "allowed": ["/approved/root/a.txt"],
        "rejected": [],
        "decisions": [],
    }
    monkeypatch.setattr(
        storage_module.cleanup_manager,
        "preflight_cleanup",
        lambda paths, roots: preview,
    )
    captured = {}

    def fake_move(paths, allowed_roots=None):
        captured["paths"] = paths
        captured["roots"] = allowed_roots
        return {
            "moved": 1,
            "failed": 0,
            "outcomes": [
                {"path": paths[0], "status": "moved", "reason": ""}
            ],
        }

    monkeypatch.setattr(
        storage_module.cleanup_manager, "move_to_recycle_bin", fake_move
    )

    class FakeReviewDialog:
        def __init__(self, preview_arg, sizes, parent=None):
            self.eligible_paths = preview_arg["allowed"]

        def exec(self):
            return QDialog.DialogCode.Accepted

    class FakeResultDialog:
        def __init__(self, result, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(storage_module, "CleanupReviewDialog", FakeReviewDialog)
    monkeypatch.setattr(storage_module, "CleanupResultDialog", FakeResultDialog)
    monkeypatch.setattr(widget, "scan_duplicates", lambda: None)

    widget.remove_duplicates()

    assert captured["paths"] == ["/approved/root/a.txt"]
    assert captured["roots"] == ["/approved/root"]


def _scan_history_record(**overrides):
    record = {
        "id": 1,
        "timestamp": "2024-01-02T03:04:05",
        "status": "completed",
        "kind": "largest",
        "root": "/data/library",
        "files_scanned": 10,
        "directories_scanned": 2,
        "bytes_processed": 2048,
        "elapsed_seconds": 65.0,
        "skipped_count": 1,
        "error": "",
    }
    record.update(overrides)
    return record


def _history_page(records, **overrides):
    result = {
        "records": records,
        "total": len(records),
        "page": 1,
        "page_size": 100,
        "page_count": 1 if records else 0,
        "has_previous": False,
        "has_next": False,
        "start_index": 1 if records else 0,
        "end_index": len(records),
        "max_id": 999,
        "filters": {},
    }
    result.update(overrides)
    return result


def test_storage_has_a_read_only_scan_history_tab(qtbot, monkeypatch):
    _app()
    monkeypatch.setattr(
        storage_module.storage_history,
        "get_scan_history_page",
        lambda **kwargs: _history_page([]),
    )
    widget = StorageScreen()
    qtbot.addWidget(widget)

    assert widget.tabs.count() == 6
    assert widget.tabs.tabText(3) == "Explorer"
    assert widget.tabs.tabText(4) == "Insights"
    assert widget.tabs.tabText(5) == "Scan History"
    assert widget.history_table.rowCount() == 0
    assert "No scan history" in widget.history_empty_label.text()
    assert widget.history_table.findChildren(QPushButton) == []


def test_scan_history_table_displays_summaries(qtbot, monkeypatch):
    _app()
    records = [
        _scan_history_record(),
        _scan_history_record(
            id=2,
            timestamp="bad timestamp",
            status="mystery",
            kind="other",
            root="",
            files_scanned="bad",
            elapsed_seconds=None,
            skipped_count=None,
        ),
    ]
    monkeypatch.setattr(
        storage_module.storage_history,
        "get_scan_history_page",
        lambda **kwargs: _history_page(records),
    )
    widget = StorageScreen()
    qtbot.addWidget(widget)

    assert widget.history_table.rowCount() == 2

    assert widget.history_table.item(0, 0).text() == "Largest Files"
    assert widget.history_table.item(0, 1).text() == "/data/library"
    assert widget.history_table.item(0, 2).text() == "Completed"
    assert widget.history_table.item(0, 3).text() == "10"
    assert widget.history_table.item(0, 4).text() == "01:05"
    assert widget.history_table.item(0, 5).text() == "2024-01-02 03:04:05"
    assert widget.history_table.item(0, 6).text() == "1"

    assert widget.history_table.item(1, 0).text() == "Unknown"
    assert widget.history_table.item(1, 1).text() == "Unknown"
    assert widget.history_table.item(1, 2).text() == "Mystery"
    assert widget.history_table.item(1, 3).text() == "0"
    assert widget.history_table.item(1, 4).text() == "00:00"
    assert widget.history_table.item(1, 5).text() == "bad timestamp"
    assert widget.history_table.item(1, 6).text() == "0"
    assert widget.history_empty_label.isHidden() is True


def test_scan_events_record_each_outcome_once(qtbot, monkeypatch):
    _app()
    calls = []
    monkeypatch.setattr(
        storage_module.storage_history,
        "get_scan_history_page",
        lambda **kwargs: _history_page([]),
    )
    monkeypatch.setattr(
        storage_module.storage_history,
        "record_scan",
        lambda payload, status: calls.append((payload, status)) or True,
    )
    widget = StorageScreen()
    qtbot.addWidget(widget)

    widget._on_scan_finished(
        {
            "generation": 1,
            "kind": "largest",
            "root": "/scan/one",
            "largest": [],
            "duplicates": [],
            "errors": [],
            "partial": False,
            "files_scanned": 1,
            "directories_scanned": 0,
            "bytes_scanned": 10,
            "elapsed_seconds": 1.0,
        }
    )
    widget._on_scan_finished(
        {
            "generation": 2,
            "kind": "duplicates",
            "root": "/scan/two",
            "largest": [],
            "duplicates": [],
            "errors": [],
            "partial": True,
            "files_scanned": 2,
            "directories_scanned": 0,
            "bytes_scanned": 20,
            "elapsed_seconds": 2.0,
        }
    )
    widget._on_scan_cancelled({"kind": "largest"})
    widget._on_scan_failed({"kind": "largest", "error": "denied"})

    assert [status for _, status in calls] == [
        "completed",
        "partial",
        "cancelled",
        "failed",
    ]
    assert len(calls) == 4


def test_history_recording_failure_does_not_affect_scan_results(
    qtbot, monkeypatch
):
    _app()

    def fail(*args, **kwargs):
        raise RuntimeError("history unavailable")

    monkeypatch.setattr(
        storage_module.storage_history,
        "get_scan_history_page",
        lambda **kwargs: _history_page([]),
    )
    monkeypatch.setattr(storage_module.storage_history, "record_scan", fail)
    widget = StorageScreen()
    qtbot.addWidget(widget)

    widget._on_scan_finished(
        {
            "generation": 1,
            "kind": "largest",
            "root": "/scan/one",
            "largest": [
                {
                    "name": "movie.mkv",
                    "path": "/scan/one/movie.mkv",
                    "size": 1024,
                    "modified": "2024-01-01 00:00:00",
                }
            ],
            "duplicates": [],
            "errors": [],
            "partial": False,
            "files_scanned": 1,
            "directories_scanned": 0,
            "bytes_scanned": 1024,
            "elapsed_seconds": 1.0,
        }
    )

    assert widget.largest_files_data[0]["name"] == "movie.mkv"
    assert widget.largest_table.item(0, 0).text() == "movie.mkv"
    assert "Scan complete" in widget.scan_status_label.text()
    assert widget._scan_roots["largest"] == "/scan/one"


def test_historical_roots_never_authorize_cleanup(qtbot, monkeypatch):
    _app()
    monkeypatch.setattr(
        storage_module.storage_history,
        "get_scan_history_page",
        lambda **kwargs: _history_page(
            [_scan_history_record(root="/historical/approved")]
        ),
    )
    widget = StorageScreen()
    qtbot.addWidget(widget)

    assert widget.history_table.rowCount() == 1
    assert widget._scan_roots == {"largest": None, "duplicates": None}
    assert widget.delete_largest_btn.isEnabled() is False
    assert widget.remove_dups_btn.isEnabled() is False


def test_storage_survives_non_finite_history_numbers(qtbot, monkeypatch):
    _app()
    records = [
        _scan_history_record(
            id=2,
            files_scanned=float("inf"),
            directories_scanned=float("-inf"),
            bytes_processed=float("inf"),
            elapsed_seconds=float("nan"),
            skipped_count=float("-inf"),
        ),
        _scan_history_record(
            id=1,
            files_scanned=float("-inf"),
            elapsed_seconds=float("inf"),
            skipped_count=float("inf"),
        ),
    ]
    monkeypatch.setattr(
        storage_module.storage_history,
        "get_scan_history_page",
        lambda **kwargs: _history_page(records),
    )

    widget = StorageScreen()
    qtbot.addWidget(widget)

    assert widget.history_table.rowCount() == 2
    for row in range(2):
        assert widget.history_table.item(row, 3).text() == "0"
        assert widget.history_table.item(row, 4).text() == "00:00"
        assert widget.history_table.item(row, 6).text() == "0"


def test_history_rendering_isolates_a_bad_row(qtbot, monkeypatch):
    _app()

    class BadNumber:
        def __bool__(self):
            return True

        def __int__(self):
            raise RuntimeError("unrenderable number")

    records = [
        _scan_history_record(id=2, elapsed_seconds=BadNumber()),
        _scan_history_record(id=1),
    ]
    monkeypatch.setattr(
        storage_module.storage_history,
        "get_scan_history_page",
        lambda **kwargs: _history_page(records),
    )

    widget = StorageScreen()
    qtbot.addWidget(widget)

    assert widget.history_table.rowCount() == 1
    assert widget.history_table.item(0, 0).text() == "Largest Files"
    assert widget.history_table.item(0, 4).text() == "01:05"

