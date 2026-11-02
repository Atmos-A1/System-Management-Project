"""Tests for the cleanup review and result dialogs."""

from PySide6.QtWidgets import QDialog

from panther.ui.cleanup_review import CleanupResultDialog, CleanupReviewDialog


def _preview():
    return {
        "decisions": [
            {"path": "/data/a.txt", "allowed": True, "reason": ""},
            {"path": "/data/b.txt", "allowed": True, "reason": ""},
            {
                "path": "/data/protected.bin",
                "allowed": False,
                "reason": "Path is in a protected system location",
            },
        ],
        "allowed": ["/data/a.txt", "/data/b.txt"],
        "rejected": [
            {
                "path": "/data/protected.bin",
                "allowed": False,
                "reason": "Path is in a protected system location",
            }
        ],
    }


def test_review_shows_exact_eligible_and_rejected_paths(qtbot):
    dialog = CleanupReviewDialog(
        _preview(), {"/data/a.txt": 100, "/data/b.txt": 2048}
    )
    qtbot.addWidget(dialog)

    assert dialog.eligible_table.rowCount() == 2
    assert dialog.rejected_table.rowCount() == 1
    assert dialog.eligible_table.item(0, 0).text() == "/data/a.txt"
    assert dialog.eligible_table.item(1, 0).text() == "/data/b.txt"
    assert dialog.eligible_table.item(1, 1).text() == "2.0 KB"
    assert dialog.rejected_table.item(0, 0).text() == "/data/protected.bin"
    assert "protected" in dialog.rejected_table.item(0, 1).text().lower()
    assert "2 files" in dialog.confirm_button.text()
    assert "2.1 KB" in dialog.summary_label.text()


def test_review_returns_only_unique_eligible_paths(qtbot):
    preview = _preview()
    preview["allowed"] = [
        "/data/a.txt",
        "/data/a.txt",
        "/data/b.txt",
    ]
    dialog = CleanupReviewDialog(preview, {"/data/a.txt": 1, "/data/b.txt": 1})
    qtbot.addWidget(dialog)

    assert dialog.eligible_table.rowCount() == 2
    assert dialog.eligible_paths == ["/data/a.txt", "/data/b.txt"]


def test_confirmation_accepts_and_cancel_leaves_no_selection(qtbot):
    dialog = CleanupReviewDialog(
        _preview(), {"/data/a.txt": 1, "/data/b.txt": 1}
    )
    qtbot.addWidget(dialog)

    dialog.confirm_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.eligible_paths == ["/data/a.txt", "/data/b.txt"]

    cancelled = CleanupReviewDialog(
        _preview(), {"/data/a.txt": 1, "/data/b.txt": 1}
    )
    qtbot.addWidget(cancelled)
    cancelled.reject()
    assert cancelled.result() == QDialog.DialogCode.Rejected


def test_no_eligible_files_disables_confirmation(qtbot):
    preview = {
        "decisions": [
            {
                "path": "/data/protected.bin",
                "allowed": False,
                "reason": "Protected system location",
            }
        ],
        "allowed": [],
        "rejected": [
            {
                "path": "/data/protected.bin",
                "allowed": False,
                "reason": "Protected system location",
            }
        ],
    }
    dialog = CleanupReviewDialog(preview, {})
    qtbot.addWidget(dialog)

    assert dialog.eligible_table.rowCount() == 0
    assert dialog.rejected_table.rowCount() == 1
    assert dialog.confirm_button.isEnabled() is False


def test_result_dialog_lists_moved_rejected_and_failed_outcomes(qtbot):
    result = {
        "moved": 1,
        "failed": 2,
        "outcomes": [
            {"path": "/data/a.txt", "status": "moved", "reason": ""},
            {
                "path": "/data/b.txt",
                "status": "rejected",
                "reason": "Path changed since scan",
            },
            {
                "path": "/data/c.txt",
                "status": "failed",
                "reason": "Permission denied",
            },
        ],
    }
    dialog = CleanupResultDialog(result)
    qtbot.addWidget(dialog)

    assert dialog.outcomes_table.rowCount() == 3
    assert dialog.outcomes_table.item(0, 1).text() == "Moved"
    assert dialog.outcomes_table.item(1, 1).text() == "Rejected"
    assert dialog.outcomes_table.item(2, 1).text() == "Failed"
    assert "Path changed" in dialog.outcomes_table.item(1, 2).text()
    assert "1" in dialog.summary_label.text()
    assert "2" in dialog.summary_label.text()
