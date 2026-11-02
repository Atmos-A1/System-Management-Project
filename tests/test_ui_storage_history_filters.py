"""Tests for Scan History filtering and pagination controls."""

import json
from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QPushButton

from panther.db import Database
from panther.services import history, storage_history
from panther.ui.storage import StorageScreen


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _insert(
    db,
    timestamp,
    kind="largest",
    status="completed",
    root="/data/library",
    **extra,
):
    detail = {
        "status": status,
        "kind": kind,
        "root": root,
        "files_scanned": extra.pop("files_scanned", 10),
        "directories_scanned": 2,
        "bytes_processed": 2048,
        "elapsed_seconds": 65.0,
        "skipped_count": extra.pop("skipped_count", 0),
    }
    detail.update(extra)
    db.execute(
        "INSERT INTO history (ts, category, detail) VALUES (?, ?, ?)",
        (timestamp, "storage_scan", json.dumps(detail)),
    )


def _seed(db):
    _insert(db, "2024-01-01T10:00:00", root="/data/one")
    _insert(
        db,
        "2024-01-02T10:00:00",
        kind="duplicates",
        status="partial",
        root="/data/two",
    )
    _insert(
        db,
        "2024-01-03T10:00:00",
        kind="duplicates",
        status="failed",
        root="/other/three",
        error="permission denied",
    )
    _insert(
        db,
        "2024-01-04T10:00:00",
        kind="analysis",
        status="cancelled",
        root="/data/four",
    )


@pytest.fixture
def history_screen(qtbot, tmp_path, monkeypatch):
    _app()
    test_db = Database(tmp_path / "history.db")
    monkeypatch.setattr(history, "db", test_db)
    history._ensure_schema()
    _seed(test_db)
    screen = StorageScreen()
    qtbot.addWidget(screen)
    return screen, test_db


def _select_kind(screen, value):
    index = screen.history_kind_filter.findData(value)
    assert index >= 0
    screen.history_kind_filter.setCurrentIndex(index)


def _select_status(screen, value):
    index = screen.history_status_filter.findData(value)
    assert index >= 0
    screen.history_status_filter.setCurrentIndex(index)


def test_history_controls_are_present_and_read_only(history_screen):
    screen, _ = history_screen

    assert screen.history_kind_filter.count() >= 4
    assert screen.history_status_filter.count() >= 5
    assert screen.history_start_date is not None
    assert screen.history_end_date is not None
    assert screen.history_search_input is not None
    assert screen.history_prev_button is not None
    assert screen.history_next_button is not None
    assert screen.history_page_label.text()
    assert screen.history_table.findChildren(QPushButton) == []

    texts = [
        button.text().casefold()
        for button in screen.scan_history_tab.findChildren(QPushButton)
    ]
    for text in texts:
        assert "delete" not in text
        assert "recycle" not in text
        assert "cleanup" not in text
        assert "move" not in text
        assert "edit" not in text


def test_filter_by_scan_type(history_screen):
    screen, _ = history_screen

    _select_kind(screen, "duplicates")

    assert screen.history_table.rowCount() == 2
    assert all(
        screen.history_table.item(row, 0).text() == "Duplicates"
        for row in range(2)
    )
    assert "2 records" in screen.history_page_label.text()


def test_filter_by_status(history_screen):
    screen, _ = history_screen

    _select_status(screen, "failed")

    assert screen.history_table.rowCount() == 1
    assert screen.history_table.item(0, 2).text() == "Failed"
    assert "/other/three" in screen.history_table.item(0, 1).text()


def test_filter_by_date_range(history_screen):
    screen, _ = history_screen

    screen.history_start_date.setDate(QDate(2024, 1, 2))
    screen.history_end_date.setDate(QDate(2024, 1, 3))

    assert screen.history_table.rowCount() == 2


def test_text_search(history_screen):
    screen, _ = history_screen

    screen.history_search_input.setText("denied")

    assert screen.history_table.rowCount() == 1
    assert screen.history_table.item(0, 2).text() == "Failed"


def test_combined_filters(history_screen):
    screen, _ = history_screen

    _select_kind(screen, "duplicates")
    _select_status(screen, "partial")
    screen.history_start_date.setDate(QDate(2024, 1, 2))
    screen.history_end_date.setDate(QDate(2024, 1, 2))

    assert screen.history_table.rowCount() == 1
    assert screen.history_table.item(0, 1).text() == "/data/two"


def test_clearing_one_filter_preserves_the_others(history_screen):
    screen, _ = history_screen

    _select_kind(screen, "duplicates")
    _select_status(screen, "partial")
    assert screen.history_table.rowCount() == 1

    _select_kind(screen, None)

    assert screen.history_status_filter.currentData() == "partial"
    assert screen.history_table.rowCount() == 1
    assert screen.history_table.item(0, 1).text() == "/data/two"

    _select_status(screen, None)
    assert screen.history_table.rowCount() == 4


def test_clear_all_restores_unfiltered_history(history_screen):
    screen, _ = history_screen

    _select_kind(screen, "duplicates")
    _select_status(screen, "failed")
    screen.history_start_date.setDate(QDate(2024, 1, 3))
    screen.history_end_date.setDate(QDate(2024, 1, 3))
    screen.history_search_input.setText("three")
    assert screen.history_table.rowCount() == 1

    screen.history_clear_filters_button.click()

    assert screen.history_kind_filter.currentData() is None
    assert screen.history_status_filter.currentData() is None
    assert screen.history_start_date.date() == (
        screen.history_start_date.minimumDate()
    )
    assert screen.history_end_date.date() == (
        screen.history_end_date.minimumDate()
    )
    assert screen.history_search_input.text() == ""
    assert screen.history_table.rowCount() == 4


def test_invalid_date_range_shows_feedback(history_screen):
    screen, _ = history_screen

    screen.history_start_date.setDate(QDate(2024, 2, 1))
    screen.history_end_date.setDate(QDate(2024, 1, 1))

    assert screen.history_error_label.isHidden() is False
    assert "start date" in screen.history_error_label.text().lower()
    assert screen.history_table.rowCount() == 0


def test_pagination_next_previous_and_range_label(history_screen):
    screen, db = history_screen
    base = datetime(2024, 2, 1, 10, 0, 0)
    for index in range(30):
        _insert(
            db,
            (base + timedelta(minutes=index)).isoformat(),
            root=f"/bulk/{index}",
        )
    screen._refresh_scan_history(reset_page=True)

    page_size = storage_history.DEFAULT_PAGE_SIZE
    assert screen.history_table.rowCount() == page_size
    assert screen.history_next_button.isEnabled() is True
    assert screen.history_prev_button.isEnabled() is False
    assert f"1-{page_size}" in screen.history_page_label.text()
    assert "34 records" in screen.history_page_label.text()

    screen.history_next_button.click()
    assert screen.history_table.rowCount() == 34 - page_size
    assert screen.history_prev_button.isEnabled() is True
    assert screen.history_next_button.isEnabled() is False
    assert "2 of 2" in screen.history_page_label.text()

    screen.history_prev_button.click()
    assert screen.history_table.rowCount() == page_size
    assert screen.history_prev_button.isEnabled() is False


def test_filter_change_resets_pagination_to_first_page(history_screen):
    screen, db = history_screen
    base = datetime(2024, 2, 1, 10, 0, 0)
    for index in range(30):
        _insert(
            db,
            (base + timedelta(minutes=index)).isoformat(),
            root=f"/bulk/{index}",
        )
    screen._refresh_scan_history(reset_page=True)
    screen.history_next_button.click()
    assert "2 of 2" in screen.history_page_label.text()

    _select_status(screen, "completed")

    assert "Page 1" in screen.history_page_label.text()
    assert screen.history_prev_button.isEnabled() is False


def test_empty_filtered_results_have_clear_state(history_screen):
    screen, _ = history_screen

    _select_kind(screen, "analysis")
    screen.history_search_input.setText("no-such-value")

    assert screen.history_table.rowCount() == 0
    assert screen.history_empty_label.isHidden() is False
    assert "matches" in screen.history_empty_label.text().lower()
    assert "0 records" in screen.history_page_label.text()


def test_refresh_preserves_active_filters(history_screen):
    screen, _ = history_screen

    _select_kind(screen, "duplicates")
    assert screen.history_table.rowCount() == 2

    screen._refresh_scan_history(reset_page=True)

    assert screen.history_kind_filter.currentData() == "duplicates"
    assert screen.history_table.rowCount() == 2


def test_loading_state_is_displayed_during_query(
    history_screen, monkeypatch
):
    screen, _ = history_screen
    original = storage_history.get_scan_history_page
    seen = {}

    def tracking(**kwargs):
        seen["label"] = screen.history_page_label.text()
        return original(**kwargs)

    monkeypatch.setattr(
        storage_history, "get_scan_history_page", tracking
    )
    screen._refresh_scan_history(reset_page=True)

    assert "loading" in seen["label"].lower()


def test_error_state_is_displayed(history_screen, monkeypatch):
    screen, _ = history_screen

    def fail(**kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        storage_history, "get_scan_history_page", fail
    )
    screen._refresh_scan_history(reset_page=True)

    assert screen.history_error_label.isHidden() is False
    assert "unavailable" in screen.history_error_label.text().lower()
    assert screen.history_table.rowCount() == 0


def test_history_filters_never_authorize_cleanup(history_screen):
    screen, _ = history_screen
    before = dict(screen._scan_roots)

    _select_kind(screen, "duplicates")
    _select_status(screen, "failed")
    screen.history_search_input.setText("three")
    screen.history_next_button.click()

    assert screen._scan_roots == before
    assert screen.delete_largest_btn.isEnabled() is False
    assert screen.remove_dups_btn.isEnabled() is False
