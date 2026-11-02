"""Tests for Storage navigation and Overview presentation."""

from PySide6.QtWidgets import QApplication, QDialog

import panther.ui.storage as storage_module
from panther.ui.storage import StorageScreen


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _payload(kind="largest", root="/scanned/root", **overrides):
    payload = {
        "generation": 1,
        "kind": kind,
        "root": root,
        "files": [],
        "largest": [],
        "duplicates": [],
        "errors": [],
        "partial": False,
        "files_scanned": 12,
        "directories_scanned": 3,
        "bytes_scanned": 2048,
        "elapsed_seconds": 5.0,
    }
    payload.update(overrides)
    return payload


def test_storage_tabs_are_overview_largest_and_duplicates(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)

    assert widget.tabs.count() == 6
    assert widget.tabs.tabText(0) == "Overview"
    assert widget.tabs.tabText(1) == "Largest Files"
    assert widget.tabs.tabText(2) == "Duplicates"
    assert widget.tabs.tabText(3) == "Explorer"
    assert widget.tabs.tabText(4) == "Insights"
    assert widget.tabs.tabText(5) == "Scan History"
    assert widget.tabs.currentIndex() == 0


def test_overview_lists_volumes_and_initial_scan_summaries(qtbot, monkeypatch):
    _app()

    class Partition:
        mountpoint = "/mnt/demo"

    class Usage:
        total = 4 * 1024 ** 3
        used = 3 * 1024 ** 3
        free = 1024 ** 3
        percent = 75.0

    monkeypatch.setattr(
        storage_module.psutil,
        "disk_partitions",
        lambda all=False: [Partition()],
    )
    monkeypatch.setattr(
        storage_module.psutil, "disk_usage", lambda mount: Usage()
    )

    widget = StorageScreen()
    qtbot.addWidget(widget)

    assert widget.disk_table.rowCount() == 1
    assert widget.disk_table.item(0, 0).text() == "/mnt/demo"
    assert widget.disk_table.item(0, 1).text() == "4.0 GB"
    assert "No scan is running" in widget.current_scan_label.text()
    assert "No completed scan" in widget.recent_scan_label.text()


def test_overview_reflects_current_and_most_recent_scan(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)

    widget._on_scan_started("largest")
    assert "Largest Files" in widget.current_scan_label.text()

    widget._on_scan_progress(
        {
            "generation": 1,
            "kind": "largest",
            "phase": "scan",
            "files_scanned": 24,
            "directories_scanned": 4,
            "bytes_scanned": 4096,
            "current_path": "/tmp/example",
            "elapsed_seconds": 2.0,
        }
    )
    assert "24" in widget.current_scan_label.text()

    widget._on_scan_finished(_payload())
    assert "No scan is running" in widget.current_scan_label.text()
    assert "Largest Files" in widget.recent_scan_label.text()
    assert "12 files" in widget.recent_scan_label.text()
    assert "/scanned/root" in widget.recent_scan_label.text()


def test_cancelled_or_failed_scan_does_not_become_recent_completed_scan(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)

    widget._on_scan_started("largest")
    widget._on_scan_cancelled({"generation": 1, "kind": "largest"})
    assert "No completed scan" in widget.recent_scan_label.text()
    assert "cancelled" in widget.current_scan_label.text().lower()

    widget._on_scan_started("duplicates")
    widget._on_scan_failed(
        {"generation": 2, "kind": "duplicates", "error": "denied"}
    )
    assert "No completed scan" in widget.recent_scan_label.text()
    assert "failed" in widget.current_scan_label.text().lower()


def test_switching_tabs_preserves_results_and_scan_roots(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)

    widget._on_scan_finished(
        _payload(
            kind="largest",
            root="/scanned/largest",
            largest=[
                {
                    "name": "movie.mkv",
                    "path": "/scanned/largest/movie.mkv",
                    "size": 1024,
                    "modified": "2024-01-01 00:00:00",
                }
            ],
        )
    )
    widget._on_scan_finished(
        _payload(
            kind="duplicates",
            root="/scanned/duplicates",
            duplicates=[
                {
                    "size": 100,
                    "count": 2,
                    "potential_savings": 100,
                    "files": [
                        {
                            "path": "/scanned/duplicates/a.txt",
                            "size": 100,
                            "modified": "2024-01-01 00:00:00",
                        },
                        {
                            "path": "/scanned/duplicates/b.txt",
                            "size": 100,
                            "modified": "2023-01-01 00:00:00",
                        },
                    ],
                }
            ],
        )
    )

    widget.tabs.setCurrentIndex(1)
    assert widget.largest_files_data[0]["name"] == "movie.mkv"
    assert widget._scan_roots["largest"] == "/scanned/largest"

    widget.tabs.setCurrentIndex(2)
    assert widget.dups_panel.group_count == 1
    assert widget._scan_roots["duplicates"] == "/scanned/duplicates"

    widget.tabs.setCurrentIndex(0)
    assert widget.largest_files_data[0]["name"] == "movie.mkv"
    assert widget.dups_panel.group_count == 1
    assert widget._scan_roots == {
        "largest": "/scanned/largest",
        "duplicates": "/scanned/duplicates",
    }


def test_cleanup_actions_require_a_successful_scan_root(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)

    assert widget.delete_largest_btn.isEnabled() is False
    assert widget.remove_dups_btn.isEnabled() is False

    widget._on_scan_started("largest")
    assert widget.delete_largest_btn.isEnabled() is False

    widget._on_scan_cancelled({"generation": 1, "kind": "largest"})
    widget._on_scan_state_changed(False)
    assert widget.delete_largest_btn.isEnabled() is False

    widget._on_scan_finished(_payload(kind="largest", root="/scanned/largest"))
    assert widget.delete_largest_btn.isEnabled() is True
    assert widget.remove_dups_btn.isEnabled() is False

    widget._on_scan_finished(
        _payload(kind="duplicates", root="/scanned/duplicates")
    )
    assert widget.remove_dups_btn.isEnabled() is True

    widget._on_scan_started("duplicates")
    assert widget._scan_roots["duplicates"] is None
    assert widget.remove_dups_btn.isEnabled() is False

    widget._on_scan_failed(
        {"generation": 3, "kind": "duplicates", "error": "denied"}
    )
    widget._on_scan_state_changed(False)
    assert widget.remove_dups_btn.isEnabled() is False


def _largest_record(root="/partial/largest"):
    return {
        "name": "movie.mkv",
        "path": f"{root}/movie.mkv",
        "size": 1024,
        "modified": "2024-01-01 00:00:00",
    }


def _duplicate_group(root="/partial/duplicates"):
    return {
        "size": 100,
        "count": 2,
        "potential_savings": 100,
        "files": [
            {
                "path": f"{root}/a.txt",
                "size": 100,
                "modified": "2024-01-01 00:00:00",
            },
            {
                "path": f"{root}/b.txt",
                "size": 100,
                "modified": "2023-01-01 00:00:00",
            },
        ],
    }


def _partial(kind, root, **overrides):
    return _payload(
        kind=kind,
        root=root,
        partial=True,
        errors=[{"path": f"{root}/denied", "error": "denied"}],
        **overrides,
    )


def test_partial_largest_scan_displays_results_but_disables_cleanup(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)
    root = "/partial/largest"

    widget._on_scan_started("largest")
    widget._on_scan_finished(
        _partial("largest", root, largest=[_largest_record(root)])
    )
    widget._on_scan_state_changed(False)

    assert widget._scan_roots["largest"] is None
    assert widget.delete_largest_btn.isEnabled() is False
    assert len(widget.largest_files_data) == 1
    assert widget.largest_table.rowCount() == 1
    assert widget.largest_table.item(0, 0).text() == "movie.mkv"


def test_partial_duplicates_scan_displays_results_but_disables_cleanup(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)
    root = "/partial/duplicates"

    widget._on_scan_started("duplicates")
    widget._on_scan_finished(
        _partial("duplicates", root, duplicates=[_duplicate_group(root)])
    )
    widget._on_scan_state_changed(False)

    assert widget._scan_roots["duplicates"] is None
    assert widget.remove_dups_btn.isEnabled() is False
    assert widget.dups_panel.group_count == 1


def test_switching_tabs_does_not_restore_partial_cleanup_authorization(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)

    widget._on_scan_finished(
        _partial(
            "largest",
            "/partial/largest",
            largest=[_largest_record("/partial/largest")],
        )
    )
    widget._on_scan_finished(
        _partial(
            "duplicates",
            "/partial/duplicates",
            duplicates=[_duplicate_group("/partial/duplicates")],
        )
    )

    for index in range(widget.tabs.count()):
        widget.tabs.setCurrentIndex(index)
        assert widget._scan_roots == {"largest": None, "duplicates": None}
        assert widget.delete_largest_btn.isEnabled() is False
        assert widget.remove_dups_btn.isEnabled() is False


def test_cancelled_and_failed_scans_remain_ineligible_for_cleanup(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)

    widget._on_scan_started("largest")
    widget._on_scan_cancelled({"generation": 1, "kind": "largest"})
    widget._on_scan_state_changed(False)
    assert widget._scan_roots["largest"] is None
    assert widget.delete_largest_btn.isEnabled() is False

    widget._on_scan_started("duplicates")
    widget._on_scan_failed(
        {"generation": 2, "kind": "duplicates", "error": "denied"}
    )
    widget._on_scan_state_changed(False)
    assert widget._scan_roots["duplicates"] is None
    assert widget.remove_dups_btn.isEnabled() is False


def test_completed_scan_after_partial_restores_cleanup_eligibility(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)

    widget._on_scan_finished(
        _partial(
            "largest",
            "/partial/largest",
            largest=[_largest_record("/partial/largest")],
        )
    )
    assert widget.delete_largest_btn.isEnabled() is False

    widget._on_scan_finished(
        _payload(
            kind="largest",
            root="/complete/largest",
            largest=[_largest_record("/complete/largest")],
        )
    )
    assert widget._scan_roots["largest"] == "/complete/largest"
    assert widget.delete_largest_btn.isEnabled() is True

    widget._on_scan_finished(
        _partial(
            "duplicates",
            "/partial/duplicates",
            duplicates=[_duplicate_group("/partial/duplicates")],
        )
    )
    assert widget.remove_dups_btn.isEnabled() is False

    widget._on_scan_finished(
        _payload(
            kind="duplicates",
            root="/complete/duplicates",
            duplicates=[_duplicate_group("/complete/duplicates")],
        )
    )
    assert widget._scan_roots["duplicates"] == "/complete/duplicates"
    assert widget.remove_dups_btn.isEnabled() is True


def test_completed_scan_cleanup_still_uses_preflight(qtbot, monkeypatch):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)
    root = "/complete/largest"

    widget._on_scan_finished(
        _payload(
            kind="largest",
            root=root,
            largest=[_largest_record(root)],
        )
    )
    widget.largest_table.selectRow(0)

    captured = {}

    def preflight(paths, roots):
        captured["paths"] = paths
        captured["roots"] = roots
        return {"allowed": [], "rejected": [], "decisions": []}

    monkeypatch.setattr(
        storage_module.cleanup_manager, "preflight_cleanup", preflight
    )

    class RejectingDialog:
        def __init__(self, preview, sizes, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(
        storage_module, "CleanupReviewDialog", RejectingDialog
    )

    widget.delete_selected_largest()

    assert captured["paths"] == [f"{root}/movie.mkv"]
    assert captured["roots"] == [root]

