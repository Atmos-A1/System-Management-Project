"""Tests for filterable, sortable model-backed Storage result views."""

import os
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from panther.ui import storage as storage_ui_module
from panther.ui.explorer import ExplorerWidget
from panther.ui.insights import InsightsWidget
from panther.ui.storage import StorageScreen


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


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


def _largest(name, path, size, modified="2024-01-01 00:00:00"):
    return {
        "name": name,
        "path": path,
        "size": size,
        "modified": modified,
    }


def _copy(path, modified, size=100):
    return {
        "name": os.path.basename(path),
        "path": path,
        "directory": os.path.dirname(path),
        "size": size,
        "modified": modified,
    }


def _duplicate_group(files, size=100, savings=None):
    return {
        "size": size,
        "count": len(files),
        "files": files,
        "potential_savings": (
            savings if savings is not None else size * (len(files) - 1)
        ),
    }


def _records(view):
    model = view.model()
    return [
        view.record_for_index(model.index(row, 0))
        for row in range(model.rowCount())
    ]


def test_largest_filtering_sorting_and_filtered_empty_state(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)
    widget._populate_largest(
        [
            _largest("alpha.txt", "/approved/root/alpha.txt", 10),
            _largest("beta.bin", "/approved/root/beta.bin", 300),
            _largest("Gamma.txt", "/other/gamma.txt", 20),
        ]
    )

    assert widget.largest_table.rowCount() == 3
    widget.largest_filter_input.setText("ALPHA")
    assert widget.largest_table.rowCount() == 1
    assert _records(widget.largest_table)[0]["path"].endswith("alpha.txt")

    widget.largest_filter_input.setText("other/")
    assert widget.largest_table.rowCount() == 1
    assert _records(widget.largest_table)[0]["name"] == "Gamma.txt"

    widget.largest_filter_input.setText("missing")
    assert widget.largest_table.rowCount() == 0
    assert "no files match" in widget.largest_filter_status.text().lower()

    widget.largest_filter_input.clear()
    assert widget.largest_table.rowCount() == 3

    widget.largest_table.sortByColumn(2, Qt.AscendingOrder)
    assert [
        item["size"] for item in _records(widget.largest_table)
    ] == [10, 20, 300]
    widget.largest_table.sortByColumn(0, Qt.DescendingOrder)
    assert [
        item["name"] for item in _records(widget.largest_table)
    ] == ["Gamma.txt", "beta.bin", "alpha.txt"]


def test_largest_selection_maps_to_source_record_after_filtering(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)
    widget._populate_largest(
        [
            _largest("alpha.txt", "/approved/root/alpha.txt", 10),
            _largest("beta.bin", "/approved/root/beta.bin", 300),
        ]
    )
    widget.largest_filter_input.setText("beta")
    widget.largest_table.selectRow(0)

    selected = widget.largest_table.selected_records()
    assert len(selected) == 1
    assert selected[0]["path"] == "/approved/root/beta.bin"


def test_largest_cleanup_uses_selected_source_records(qtbot, monkeypatch):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)
    widget._scan_roots["largest"] = "/approved/root"
    widget._populate_largest(
        [
            _largest("alpha.txt", "/approved/root/alpha.txt", 10),
            _largest("beta.bin", "/approved/root/beta.bin", 300),
        ]
    )
    widget.largest_filter_input.setText("alpha")
    widget.largest_table.selectRow(0)

    captured = {}
    preview = {
        "allowed": ["/approved/root/alpha.txt"],
        "rejected": [],
        "decisions": [],
    }

    def preflight(paths, roots):
        captured["paths"] = list(paths)
        captured["roots"] = list(roots)
        return preview

    monkeypatch.setattr(
        storage_ui_module.cleanup_manager,
        "preflight_cleanup",
        preflight,
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

    def fake_move(paths, allowed_roots=None):
        captured["moved"] = list(paths)
        return {"moved": 1, "failed": 0, "outcomes": []}

    monkeypatch.setattr(
        storage_ui_module, "CleanupReviewDialog", FakeReviewDialog
    )
    monkeypatch.setattr(
        storage_ui_module, "CleanupResultDialog", FakeResultDialog
    )
    monkeypatch.setattr(
        storage_ui_module.cleanup_manager,
        "move_to_recycle_bin",
        fake_move,
    )
    monkeypatch.setattr(widget, "scan_largest_files", lambda: None)

    widget.delete_selected_largest()

    assert captured["paths"] == ["/approved/root/alpha.txt"]
    assert captured["moved"] == ["/approved/root/alpha.txt"]
    assert captured["roots"] == ["/approved/root"]


def test_duplicate_filtering_sorting_and_group_identity(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)
    first = _duplicate_group(
        [
            _copy("/data/first-a.txt", "2024-01-02 00:00:00"),
            _copy("/data/first-b.txt", "2020-01-01 00:00:00"),
        ],
        size=100,
    )
    second = _duplicate_group(
        [
            _copy("/other/second-a.bin", "2023-01-01 00:00:00", size=500),
            _copy("/other/second-b.bin", "2019-01-01 00:00:00", size=500),
        ],
        size=500,
    )
    widget._populate_duplicates([first, second])
    panel = widget.dups_panel

    assert panel.group_table.rowCount() == 2
    panel.group_filter_input.setText("second-a")
    assert panel.group_table.rowCount() == 1
    selected = panel.group_table.record_for_index(
        panel.group_table.model().index(0, 0)
    )
    assert selected["files"][0]["path"].startswith("/other/")

    panel.group_filter_input.clear()
    panel.group_table.sortByColumn(1, Qt.AscendingOrder)
    ordered = _records(panel.group_table)
    assert [group["size"] for group in ordered] == [100, 500]

    panel.group_table.selectRow(1)
    assert panel.current_selection is not None
    assert panel.current_selection.copies[0]["path"].startswith("/other/")
    assert panel.current_selection.keep_newest() == "/other/second-a.bin"
    assert panel.removal_paths == [
        "/other/second-b.bin"
    ]


def test_duplicate_filtering_does_not_select_hidden_removals(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)
    widget._populate_duplicates(
        [
            _duplicate_group(
                [
                    _copy("/data/a.txt", "2024-01-01 00:00:00"),
                    _copy("/data/b.txt", "2023-01-01 00:00:00"),
                ]
            ),
            _duplicate_group(
                [
                    _copy("/other/c.txt", "2024-01-01 00:00:00"),
                    _copy("/other/d.txt", "2023-01-01 00:00:00"),
                ]
            ),
        ]
    )
    panel = widget.dups_panel
    panel.group_filter_input.setText("other/")
    panel.group_table.selectRow(0)

    assert panel.removal_paths == []
    assert panel.current_selection.copies[0]["path"].startswith("/other/")


def test_duplicate_cleanup_receives_selected_source_paths(qtbot, monkeypatch):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)
    widget._scan_roots["duplicates"] = "/approved/root"
    widget._populate_duplicates(
        [
            _duplicate_group(
                [
                    _copy(
                        "/approved/root/a.txt", "2024-01-01 00:00:00"
                    ),
                    _copy(
                        "/approved/root/b.txt", "2023-01-01 00:00:00"
                    ),
                ]
            )
        ]
    )
    panel = widget.dups_panel
    panel.group_filter_input.setText("b.txt")
    panel.group_table.selectRow(0)
    assert panel.current_selection.set_remove("/approved/root/a.txt", True)
    panel.refresh_current_selection()

    captured = {}
    preview = {
        "allowed": ["/approved/root/a.txt"],
        "rejected": [],
        "decisions": [],
    }

    def preflight(paths, roots):
        captured["paths"] = list(paths)
        captured["roots"] = list(roots)
        return preview

    monkeypatch.setattr(
        storage_ui_module.cleanup_manager,
        "preflight_cleanup",
        preflight,
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

    def fake_move(paths, allowed_roots=None):
        captured["moved"] = list(paths)
        return {"moved": 1, "failed": 0, "outcomes": []}

    monkeypatch.setattr(
        storage_ui_module, "CleanupReviewDialog", FakeReviewDialog
    )
    monkeypatch.setattr(
        storage_ui_module, "CleanupResultDialog", FakeResultDialog
    )
    monkeypatch.setattr(
        storage_ui_module.cleanup_manager,
        "move_to_recycle_bin",
        fake_move,
    )
    monkeypatch.setattr(widget, "scan_duplicates", lambda: None)

    widget.remove_duplicates()

    assert captured["paths"] == ["/approved/root/a.txt"]
    assert captured["moved"] == ["/approved/root/a.txt"]
    assert captured["roots"] == ["/approved/root"]


def test_explorer_filtering_sorting_and_selection(qtbot, tmp_path):
    _app()
    for name, size in [
        ("alpha.txt", 3),
        ("beta.bin", 50),
        ("gamma.txt", 5),
    ]:
        (tmp_path / name).write_bytes(b"x" * size)
    folder = tmp_path / "folder"
    folder.mkdir()

    explorer = ExplorerWidget(initial_path=str(tmp_path))
    qtbot.addWidget(explorer)
    _wait_listing(qtbot, explorer)

    explorer.filter_input.setText("ALPHA")
    assert explorer.table.rowCount() == 1
    assert _records(explorer.table)[0]["name"] == "alpha.txt"

    explorer.table.selectRow(0)
    _wait_inspection(qtbot, explorer)
    assert explorer.detail_name_label.text() == "alpha.txt"
    assert explorer.detail_path_label.text() == str(tmp_path / "alpha.txt")

    explorer.filter_input.setText("")
    assert explorer.table.rowCount() == 4
    explorer.table.sortByColumn(2, Qt.DescendingOrder)
    first = _records(explorer.table)[0]
    assert first["type"] == "file"
    assert first["size"] == 50

    explorer.table.selectRow(0)
    _wait_inspection(qtbot, explorer)
    assert explorer.detail_name_label.text() == "beta.bin"
    assert explorer.detail_path_label.text() == str(tmp_path / "beta.bin")
    assert explorer.current_path == str(tmp_path)


def test_explorer_filter_clears_without_changing_navigation_history(
    qtbot, tmp_path
):
    _app()
    root = tmp_path / "root"
    sub = root / "sub"
    sub.mkdir(parents=True)
    (sub / "child.txt").write_text("x")

    explorer = ExplorerWidget(initial_path=str(root))
    qtbot.addWidget(explorer)
    _wait_listing(qtbot, explorer)
    explorer.navigate_to(str(sub))
    _wait_listing(qtbot, explorer)
    assert explorer.back_button.isEnabled() is True

    explorer.filter_input.setText("missing")
    assert explorer.table.rowCount() == 0
    assert explorer.current_path == str(sub)

    explorer.filter_input.clear()
    assert explorer.table.rowCount() == 1
    assert explorer.current_path == str(sub)
    explorer.back_button.click()
    _wait_listing(qtbot, explorer)
    assert explorer.current_path == str(root)


def test_insights_folder_filter_sort_and_navigation(qtbot, tmp_path):
    _app()
    first = tmp_path / "alpha"
    second = tmp_path / "beta"
    first.mkdir()
    second.mkdir()
    panel = InsightsWidget(initial_path=str(tmp_path))
    qtbot.addWidget(panel)
    panel._populate_folders(
        [
            {
                "name": "alpha",
                "path": str(first),
                "size": 10,
                "file_count": 1,
                "status": "complete",
            },
            {
                "name": "beta",
                "path": str(second),
                "size": 500,
                "file_count": 5,
                "status": "partial",
            },
        ]
    )

    panel.folder_filter_input.setText("BETA")
    assert panel.folder_table.rowCount() == 1
    panel.folder_table.sortByColumn(2, Qt.AscendingOrder)
    panel.folder_table.selectRow(0)
    captured = []
    panel.folder_opened.connect(captured.append)
    panel.open_folder_button.click()

    assert captured == [str(second)]

    panel.folder_filter_input.clear()
    assert panel.folder_table.rowCount() == 2
    panel.folder_table.sortByColumn(2, Qt.AscendingOrder)
    assert [
        item["size"] for item in _records(panel.folder_table)
    ] == [10, 500]


def test_insights_file_type_filter_sort_and_values(qtbot):
    _app()
    panel = InsightsWidget()
    qtbot.addWidget(panel)
    panel._populate_file_types(
        [
            {
                "key": ".pdf",
                "label": ".pdf",
                "count": 2,
                "size": 100,
                "percentage": 20.0,
            },
            {
                "key": ".png",
                "label": ".png",
                "count": 5,
                "size": 400,
                "percentage": 80.0,
            },
        ]
    )

    panel.file_type_filter_input.setText("PDF")
    assert panel.file_type_table.rowCount() == 1
    assert _records(panel.file_type_table)[0]["key"] == ".pdf"

    panel.file_type_filter_input.clear()
    assert panel.file_type_table.rowCount() == 2
    panel.file_type_table.sortByColumn(1, Qt.DescendingOrder)
    assert [
        item["count"] for item in _records(panel.file_type_table)
    ] == [5, 2]
    panel.file_type_table.sortByColumn(3, Qt.AscendingOrder)
    assert [
        item["percentage"] for item in _records(panel.file_type_table)
    ] == [20.0, 80.0]


def test_large_largest_result_set_remains_mapped_and_responsive(qtbot):
    _app()
    widget = StorageScreen()
    qtbot.addWidget(widget)
    records = [
        _largest(
            f"file-{index:04d}.bin",
            f"/approved/root/file-{index:04d}.bin",
            index,
        )
        for index in range(2000)
    ]

    started = time.monotonic()
    widget._populate_largest(records)
    assert widget.largest_table.rowCount() == 2000
    widget.largest_filter_input.setText("file-1999")
    assert widget.largest_table.rowCount() == 1
    widget.largest_table.selectRow(0)
    assert widget.largest_table.selected_records()[0]["size"] == 1999
    widget.largest_filter_input.clear()
    widget.largest_table.sortByColumn(2, Qt.DescendingOrder)
    assert _records(widget.largest_table)[0]["size"] == 1999
    assert time.monotonic() - started < 5.0
