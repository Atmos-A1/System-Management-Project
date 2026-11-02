"""Tests for persistent Storage scan history summaries."""

import json
import math

from panther.services import storage_history


def _capture_events(monkeypatch):
    events = []

    def record(category, detail):
        events.append((category, detail))

    monkeypatch.setattr(storage_history.history, "record_event", record)
    return events


def _payload(**overrides):
    payload = {
        "kind": "largest",
        "root": "/data/library",
        "files_scanned": 12,
        "directories_scanned": 3,
        "bytes_scanned": 2048,
        "elapsed_seconds": 5.0,
        "errors": [{"path": "/data/denied", "error": "denied"}],
        "largest": [
            {"path": "/data/library/movie.mkv", "size": 4096}
        ],
        "duplicates": [
            {"files": [{"path": "/data/a.txt"}, {"path": "/data/b.txt"}]}
        ],
    }
    payload.update(overrides)
    return payload


def test_completed_scan_is_recorded_as_summary_only(monkeypatch):
    events = _capture_events(monkeypatch)

    assert storage_history.record_scan(_payload(), "completed") is True
    assert len(events) == 1

    category, detail = events[0]
    assert category == "storage_scan"
    data = json.loads(detail)
    assert data["status"] == "completed"
    assert data["kind"] == "largest"
    assert data["root"] == "/data/library"
    assert data["files_scanned"] == 12
    assert data["directories_scanned"] == 3
    assert data["bytes_processed"] == 2048
    assert data["elapsed_seconds"] == 5.0
    assert data["skipped_count"] == 1
    assert "largest" not in data
    assert "duplicates" not in data
    assert "files" not in data
    assert "/data/library/movie.mkv" not in detail


def test_partial_cancelled_and_failed_scans_are_recorded(monkeypatch):
    events = _capture_events(monkeypatch)

    storage_history.record_scan(_payload(partial=True), "partial")
    storage_history.record_scan(
        {"kind": "duplicates", "root": "/data"}, "cancelled"
    )
    storage_history.record_scan(
        {"kind": "largest", "root": "/data", "error": "permission denied"},
        "failed",
    )

    records = [json.loads(detail) for _, detail in events]
    assert [item["status"] for item in records] == [
        "partial",
        "cancelled",
        "failed",
    ]
    assert records[1]["kind"] == "duplicates"
    assert records[2]["error"] == "permission denied"


def test_missing_optional_fields_are_normalised(monkeypatch):
    events = _capture_events(monkeypatch)

    assert storage_history.record_scan({"kind": "duplicates"}, "completed")
    data = json.loads(events[0][1])

    assert data["root"] == ""
    assert data["files_scanned"] == 0
    assert data["directories_scanned"] == 0
    assert data["bytes_processed"] == 0
    assert data["elapsed_seconds"] == 0
    assert data["skipped_count"] == 0


def test_recording_failure_is_best_effort(monkeypatch):
    def fail(category, detail):
        raise RuntimeError("history unavailable")

    monkeypatch.setattr(storage_history.history, "record_event", fail)

    assert storage_history.record_scan(_payload(), "completed") is False


def test_get_scan_history_filters_and_parses_records(monkeypatch):
    rows = [
        (
            3,
            "2024-01-03T10:00:00",
            "storage_scan",
            json.dumps(
                {
                    "status": "failed",
                    "kind": "duplicates",
                    "root": "/data/b",
                    "files_scanned": 3,
                    "directories_scanned": 1,
                    "bytes_processed": 300,
                    "elapsed_seconds": 2,
                    "skipped_count": 4,
                    "error": "denied",
                }
            ),
        ),
        (2, "2024-01-02T10:00:00", "action", "not storage"),
        (
            1,
            "2024-01-01T10:00:00",
            "storage_scan",
            json.dumps(
                {
                    "status": "completed",
                    "kind": "largest",
                    "root": "/data/a",
                    "files_scanned": 10,
                }
            ),
        ),
    ]
    monkeypatch.setattr(
        storage_history.history, "get_recent", lambda limit: rows
    )

    records = storage_history.get_scan_history(limit=10)

    assert len(records) == 2
    assert records[0]["id"] == 3
    assert records[0]["status"] == "failed"
    assert records[0]["kind"] == "duplicates"
    assert records[0]["skipped_count"] == 4
    assert records[1]["id"] == 1
    assert records[1]["bytes_processed"] == 0


def test_malformed_records_and_unknown_status_are_safe(monkeypatch):
    rows = [
        (4, "2024-01-04T10:00:00", "storage_scan", "not-json"),
        (3, "2024-01-03T10:00:00", "storage_scan", "[]"),
        (
            2,
            "2024-01-02T10:00:00",
            "storage_scan",
            json.dumps({"status": "mystery", "kind": "other"}),
        ),
        (
            1,
            "2024-01-01T10:00:00",
            "storage_scan",
            json.dumps({"status": None, "files_scanned": "bad"}),
        ),
    ]
    monkeypatch.setattr(
        storage_history.history, "get_recent", lambda limit: rows
    )

    records = storage_history.get_scan_history(limit=10)

    assert len(records) == 4
    assert records[0]["status"] == "unknown"
    assert records[0]["kind"] == "unknown"
    assert records[1]["status"] == "unknown"
    assert records[2]["status"] == "mystery"
    assert records[3]["files_scanned"] == 0


def test_history_read_is_bounded(monkeypatch):
    requested = {}

    def get_recent(limit):
        requested["limit"] = limit
        return []

    monkeypatch.setattr(storage_history.history, "get_recent", get_recent)

    storage_history.get_scan_history(limit=20)

    assert requested["limit"] >= 20
    assert requested["limit"] <= 1000


def _stored_row(row_id, **values):
    return (
        row_id,
        f"2024-01-0{row_id}T10:00:00",
        "storage_scan",
        json.dumps(values),
    )


def test_non_finite_history_numbers_are_normalised(monkeypatch):
    rows = [
        _stored_row(
            4,
            status="completed",
            kind="largest",
            files_scanned=float("inf"),
            directories_scanned=float("-inf"),
            bytes_processed=float("inf"),
            elapsed_seconds=float("nan"),
            skipped_count=float("-inf"),
        ),
        _stored_row(
            3,
            status="completed",
            kind="duplicates",
            files_scanned=float("-inf"),
            elapsed_seconds=float("inf"),
        ),
        _stored_row(
            2,
            status="completed",
            kind="largest",
            files_scanned="Infinity",
            elapsed_seconds="-Infinity",
            skipped_count="NaN",
        ),
        _stored_row(
            1,
            status="completed",
            kind="largest",
            files_scanned=3,
            directories_scanned=1,
            bytes_processed=12,
            elapsed_seconds=2.5,
            skipped_count=0,
        ),
    ]
    monkeypatch.setattr(
        storage_history.history, "get_recent", lambda limit: rows
    )

    records = storage_history.get_scan_history(limit=10)

    assert len(records) == 4
    for record in records:
        assert math.isfinite(record["elapsed_seconds"])
        assert math.isfinite(record["files_scanned"])
        assert math.isfinite(record["directories_scanned"])
        assert math.isfinite(record["bytes_processed"])
        assert math.isfinite(record["skipped_count"])

    assert records[0]["files_scanned"] == 0
    assert records[0]["elapsed_seconds"] == 0.0
    assert records[0]["skipped_count"] == 0
    assert records[3]["files_scanned"] == 3
    assert records[3]["bytes_processed"] == 12
    assert records[3]["elapsed_seconds"] == 2.5


def test_record_scan_normalises_non_finite_payload(monkeypatch):
    events = _capture_events(monkeypatch)

    assert storage_history.record_scan(
        _payload(
            files_scanned=float("inf"),
            directories_scanned=float("-inf"),
            bytes_scanned=float("inf"),
            elapsed_seconds=float("nan"),
            skipped_count=float("-inf"),
        ),
        "completed",
    )

    data = json.loads(events[0][1])
    for field in (
        "files_scanned",
        "directories_scanned",
        "bytes_processed",
        "elapsed_seconds",
        "skipped_count",
    ):
        assert math.isfinite(data[field]), field
    assert data["files_scanned"] == 0
    assert data["elapsed_seconds"] == 0.0

