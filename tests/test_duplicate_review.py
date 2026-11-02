"""Tests for deliberate duplicate copy selection."""

import copy

from PySide6.QtCore import Qt

from panther.ui.duplicate_review import DuplicateReviewWidget, DuplicateSelection


def _copy(path, modified=None, size=100):
    return {
        "name": path.rsplit("/", 1)[-1],
        "path": path,
        "directory": path.rsplit("/", 1)[0],
        "size": size,
        "modified": modified,
    }


def _group(paths=None):
    files = [
        _copy("/data/new.txt", "2024-01-02 00:00:00"),
        _copy("/data/old.txt", "2020-01-01 00:00:00"),
        _copy("/data/mid.txt", "2022-01-01 00:00:00"),
    ]
    if paths is not None:
        files = paths
    return {
        "size": 100,
        "count": len(files),
        "files": files,
        "potential_savings": 200,
    }


def test_no_removals_are_selected_by_default():
    selection = DuplicateSelection(_group())

    assert selection.removal_count == 0
    assert selection.removal_paths == []
    assert selection.savings == 0
    assert len(selection.retained_paths) == 3


def test_cannot_remove_every_copy():
    selection = DuplicateSelection(_group())

    assert selection.set_remove("/data/new.txt", True) is True
    assert selection.set_remove("/data/old.txt", True) is True
    assert selection.set_remove("/data/mid.txt", True) is False

    assert selection.removal_count == 2
    assert selection.retained_paths == ["/data/mid.txt"]


def test_removal_count_and_savings_follow_selection():
    selection = DuplicateSelection(_group())

    selection.set_remove("/data/new.txt", True)
    selection.set_remove("/data/old.txt", True)

    assert selection.removal_count == 2
    assert selection.savings == 200
    assert selection.retained_paths == ["/data/mid.txt"]


def test_keep_newest_and_oldest_are_deterministic():
    selection = DuplicateSelection(_group())

    assert selection.keep_newest() == "/data/new.txt"
    assert selection.retained_paths == ["/data/new.txt"]
    assert selection.keep_oldest() == "/data/old.txt"
    assert selection.retained_paths == ["/data/old.txt"]


def test_keep_shortest_path_and_tie_breaking():
    files = [
        _copy("/data/long-name.txt", "2024-01-01 00:00:00"),
        _copy("/data/short.txt", "2024-01-01 00:00:00"),
        _copy("/data/tie.txt", "2024-01-01 00:00:00"),
    ]
    selection = DuplicateSelection(_group(files))

    assert selection.keep_shortest_path() == "/data/tie.txt"
    assert selection.keep_newest() == "/data/tie.txt"
    assert selection.keep_oldest() == "/data/tie.txt"


def test_missing_timestamps_are_handled_safely():
    files = [
        _copy("/data/known.txt", "2022-01-01 00:00:00"),
        _copy("/data/missing.txt", None),
        _copy("/data/also-missing.txt", ""),
    ]
    selection = DuplicateSelection(_group(files))

    assert selection.keep_newest() == "/data/known.txt"
    assert selection.keep_oldest() == "/data/known.txt"

    all_missing = DuplicateSelection(
        _group([_copy("/data/b.txt"), _copy("/data/a.txt")])
    )
    assert all_missing.keep_newest() == "/data/a.txt"
    assert all_missing.keep_oldest() == "/data/a.txt"


def test_selection_does_not_mutate_detection_records():
    group = _group()
    original = copy.deepcopy(group)
    selection = DuplicateSelection(group)

    selection.keep_newest()
    selection.set_remove("/data/old.txt", True)

    assert group == original


def test_group_switch_preserves_selection_predictably(qtbot):
    first = _group()
    second = {
        **_group(),
        "files": [
            _copy("/other/a.txt"),
            _copy("/other/b.txt"),
        ],
    }
    widget = DuplicateReviewWidget()
    qtbot.addWidget(widget)
    widget.set_groups([first, second])

    widget.select_group(0)
    widget.current_selection.set_remove("/data/new.txt", True)
    assert widget.removal_paths == ["/data/new.txt"]

    widget.select_group(1)
    assert widget.removal_paths == []
    assert widget.current_selection.removal_count == 0

    widget.select_group(0)
    assert widget.removal_paths == ["/data/new.txt"]


def test_malformed_and_empty_groups_are_ignored(qtbot):
    widget = DuplicateReviewWidget()
    qtbot.addWidget(widget)

    widget.set_groups(
        [
            None,
            {"files": []},
            {"files": [{"path": "/a"}, {"path": "/a"}]},
        ]
    )

    assert widget.group_table.rowCount() == 0
    assert widget.current_selection is None
    assert widget.removal_paths == []


def test_checkbox_selection_stops_before_removing_every_copy(qtbot):
    widget = DuplicateReviewWidget()
    qtbot.addWidget(widget)
    widget.set_groups([_group()])

    widget.copy_table.item(0, 4).setCheckState(Qt.Checked)
    widget.copy_table.item(1, 4).setCheckState(Qt.Checked)
    assert widget.removal_paths == ["/data/new.txt", "/data/old.txt"]

    widget.copy_table.item(2, 4).setCheckState(Qt.Checked)
    assert widget.copy_table.item(2, 4).checkState() == Qt.Unchecked
    assert widget.removal_paths == ["/data/new.txt", "/data/old.txt"]
    assert "At least one" in widget.status_label.text()


def test_widget_removal_selection_matches_current_group(qtbot):
    widget = DuplicateReviewWidget()
    qtbot.addWidget(widget)
    widget.set_groups([_group()])

    widget.current_selection.set_remove("/data/new.txt", True)
    widget.refresh_current_selection()

    assert widget.removal_paths == ["/data/new.txt"]
    assert widget.summary_label.text()
