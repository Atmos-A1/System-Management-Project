"""Tests for bounded, filterable Scan History queries."""

import json
import time
from datetime import datetime, timedelta

import pytest

from panther.db import Database
from panther.services import history, storage_history


@pytest.fixture
def isolated_history(tmp_path, monkeypatch):
    test_db = Database(tmp_path / "history.db")
    monkeypatch.setattr(history, "db", test_db)
    history._ensure_schema()
    return test_db


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
        "directories_scanned": extra.pop("directories_scanned", 2),
        "bytes_processed": extra.pop("bytes_processed", 2048),
        "elapsed_seconds": extra.pop("elapsed_seconds", 65.0),
        "skipped_count": extra.pop("skipped_count", 0),
    }
    detail.update(extra)
    db.execute(
        "INSERT INTO history (ts, category, detail) VALUES (?, ?, ?)",
        (
            timestamp,
            extra.pop("category", "storage_scan"),
            json.dumps(detail),
        ),
    )


def _seed(db):
    _insert(db, "2024-01-01T10:00:00", root="/data/one", files_scanned=1)
    _insert(
        db,
        "2024-01-02T10:00:00",
        kind="duplicates",
        status="partial",
        root="/data/two",
        skipped_count=2,
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
    _insert(db, "2024-01-05T10:00:00", category="action", root="/ignored")


def test_existing_records_remain_readable_and_unrelated_events_excluded(
    isolated_history,
):
    _seed(isolated_history)

    result = storage_history.get_scan_history_page(page=1, page_size=10)

    assert result["total"] == 4
    assert result["page"] == 1
    assert result["page_count"] == 1
    assert [record["kind"] for record in result["records"]] == [
        "analysis",
        "duplicates",
        "duplicates",
        "largest",
    ]
    assert result["records"][0]["id"] > result["records"][-1]["id"]


def test_filter_by_kind_and_status(isolated_history):
    _seed(isolated_history)

    duplicates = storage_history.get_scan_history_page(
        page=1, page_size=10, kind="duplicates"
    )
    assert duplicates["total"] == 2
    assert {record["kind"] for record in duplicates["records"]} == {
        "duplicates"
    }

    failed = storage_history.get_scan_history_page(
        page=1, page_size=10, status="failed"
    )
    assert failed["total"] == 1
    assert failed["records"][0]["status"] == "failed"


def test_filter_by_date_range_and_combined_filters(isolated_history):
    _seed(isolated_history)

    ranged = storage_history.get_scan_history_page(
        page=1,
        page_size=10,
        start_date="2024-01-02",
        end_date="2024-01-03",
    )
    assert ranged["total"] == 2
    assert {record["root"] for record in ranged["records"]} == {
        "/data/two",
        "/other/three",
    }

    combined = storage_history.get_scan_history_page(
        page=1,
        page_size=10,
        kind="duplicates",
        status="partial",
        start_date="2024-01-02",
        end_date="2024-01-02",
    )
    assert combined["total"] == 1
    assert combined["records"][0]["root"] == "/data/two"


def test_text_search_covers_summary_fields_and_is_parameterized(
    isolated_history,
):
    _seed(isolated_history)

    by_root = storage_history.get_scan_history_page(
        page=1, page_size=10, search="ONE"
    )
    assert by_root["total"] == 1

    by_error = storage_history.get_scan_history_page(
        page=1, page_size=10, search="denied"
    )
    assert by_error["total"] == 1
    assert by_error["records"][0]["status"] == "failed"

    by_kind = storage_history.get_scan_history_page(
        page=1, page_size=10, search="analysis"
    )
    assert by_kind["total"] == 1

    _insert(isolated_history, "2024-01-06T10:00:00", root="100% complete")
    assert (
        storage_history.get_scan_history_page(
            page=1, page_size=10, search="100%"
        )["total"]
        == 1
    )
    assert (
        storage_history.get_scan_history_page(
            page=1, page_size=10, search="' OR 1=1 --"
        )["total"]
        == 0
    )


def test_invalid_date_ranges_are_rejected(isolated_history):
    _seed(isolated_history)

    with pytest.raises(ValueError):
        storage_history.get_scan_history_page(
            page=1, page_size=10, start_date="not-a-date"
        )

    with pytest.raises(ValueError):
        storage_history.get_scan_history_page(
            page=1,
            page_size=10,
            start_date="2024-02-01",
            end_date="2024-01-01",
        )


def test_empty_results_have_safe_boundaries(isolated_history):
    _seed(isolated_history)

    result = storage_history.get_scan_history_page(
        page=3, page_size=10, kind="missing"
    )

    assert result["records"] == []
    assert result["total"] == 0
    assert result["page"] == 1
    assert result["page_count"] == 0
    assert result["has_previous"] is False
    assert result["has_next"] is False
    assert result["start_index"] == 0
    assert result["end_index"] == 0


def test_pagination_first_middle_and_final_pages(isolated_history):
    base = datetime(2024, 1, 1, 10, 0, 0)
    for index in range(7):
        _insert(
            isolated_history,
            (base + timedelta(minutes=index)).isoformat(),
            root=f"/data/{index}",
        )

    first = storage_history.get_scan_history_page(page=1, page_size=3)
    middle = storage_history.get_scan_history_page(page=2, page_size=3)
    final = storage_history.get_scan_history_page(page=3, page_size=3)

    assert first["total"] == 7
    assert first["page_count"] == 3
    assert [record["root"] for record in first["records"]] == [
        "/data/6",
        "/data/5",
        "/data/4",
    ]
    assert first["start_index"] == 1
    assert first["end_index"] == 3
    assert first["has_previous"] is False
    assert first["has_next"] is True

    assert [record["root"] for record in middle["records"]] == [
        "/data/3",
        "/data/2",
        "/data/1",
    ]
    assert middle["has_previous"] is True
    assert middle["has_next"] is True

    assert [record["root"] for record in final["records"]] == ["/data/0"]
    assert final["start_index"] == 7
    assert final["end_index"] == 7
    assert final["has_previous"] is True
    assert final["has_next"] is False

    clamped = storage_history.get_scan_history_page(page=99, page_size=3)
    assert clamped["page"] == 3
    assert clamped["records"][0]["root"] == "/data/0"


def test_stable_ordering_for_equal_timestamps(isolated_history):
    for index in range(3):
        _insert(
            isolated_history,
            "2024-01-01T10:00:00",
            root=f"/same/{index}",
        )

    result = storage_history.get_scan_history_page(page=1, page_size=10)

    ids = [record["id"] for record in result["records"]]
    assert ids == sorted(ids, reverse=True)
    assert [record["root"] for record in result["records"]] == [
        "/same/2",
        "/same/1",
        "/same/0",
    ]


def test_new_event_insertion_does_not_shift_an_anchored_page(
    isolated_history,
):
    base = datetime(2024, 1, 1, 10, 0, 0)
    for index in range(4):
        _insert(
            isolated_history,
            (base + timedelta(minutes=index)).isoformat(),
            root=f"/original/{index}",
        )

    first = storage_history.get_scan_history_page(page=1, page_size=2)
    anchor = first["max_id"]
    assert [record["root"] for record in first["records"]] == [
        "/original/3",
        "/original/2",
    ]

    _insert(
        isolated_history,
        "2024-01-01T11:00:00",
        root="/new/event",
    )

    second = storage_history.get_scan_history_page(
        page=2, page_size=2, max_id=anchor
    )

    assert second["total"] == 4
    assert [record["root"] for record in second["records"]] == [
        "/original/1",
        "/original/0",
    ]

    refreshed = storage_history.get_scan_history_page(page=1, page_size=10)
    assert refreshed["total"] == 5
    assert refreshed["records"][0]["root"] == "/new/event"


def test_sql_uses_placeholders_for_user_values(isolated_history, monkeypatch):
    _seed(isolated_history)
    calls = []
    real_fetchall = isolated_history.fetchall

    def tracking_fetchall(sql, params=()):
        calls.append((sql, tuple(params)))
        return real_fetchall(sql, params)

    monkeypatch.setattr(isolated_history, "fetchall", tracking_fetchall)

    storage_history.get_scan_history_page(
        page=1, page_size=10, kind="duplicates", search="data"
    )

    page_sql, page_params = calls[-1]
    assert "duplicates" not in page_sql
    assert "data" not in page_sql
    assert "duplicates" in page_params
    assert any("%data%" in str(value) for value in page_params)
    assert "LIMIT ? OFFSET ?" in page_sql


def test_history_queries_release_database_connections(
    isolated_history, monkeypatch
):
    import sqlite3

    _seed(isolated_history)
    connections = []
    real_connect = isolated_history._connect

    def tracking_connect():
        connection = real_connect()
        connections.append(connection)
        return connection

    monkeypatch.setattr(isolated_history, "_connect", tracking_connect)

    storage_history.get_scan_history_page(page=1, page_size=10)

    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")


def test_large_history_is_bounded_and_responsive(isolated_history):
    base = datetime(2024, 1, 1, 0, 0, 0)
    for index in range(300):
        _insert(
            isolated_history,
            (base + timedelta(minutes=index)).isoformat(),
            kind="duplicates" if index % 2 else "largest",
            root=f"/bulk/{index}",
        )

    started = time.monotonic()
    result = storage_history.get_scan_history_page(page=5, page_size=25)
    elapsed = time.monotonic() - started

    assert result["total"] == 300
    assert result["page_count"] == 12
    assert len(result["records"]) == 25
    assert result["start_index"] == 101
    assert result["end_index"] == 125
    assert elapsed < 5.0
