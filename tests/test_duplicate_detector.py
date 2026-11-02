"""Tests for size-filtered, cancellable duplicate detection."""

import copy
import os
import threading

import pytest

from panther.services.duplicate_detector import DuplicateDetector


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _record(path):
    return {
        "name": path.name,
        "path": str(path),
        "directory": str(path.parent),
        "size": path.stat().st_size,
        "extension": path.suffix.lower(),
        "is_file": True,
    }


def test_exact_duplicates_are_grouped(tmp_path):
    first = _write(tmp_path / "a.txt", b"same content")
    second = _write(tmp_path / "sub" / "b.txt", b"same content")
    files = [_record(first), _record(second)]

    groups = DuplicateDetector().find_duplicates(files)

    assert len(groups) == 1
    assert groups[0]["count"] == 2
    assert groups[0]["size"] == len(b"same content")
    assert groups[0]["potential_savings"] == len(b"same content")
    assert {item["path"] for item in groups[0]["files"]} == {
        str(first),
        str(second),
    }


def test_same_size_different_content_is_not_duplicate(tmp_path):
    files = [
        _record(_write(tmp_path / "a.bin", b"aaaa")),
        _record(_write(tmp_path / "b.bin", b"bbbb")),
    ]

    assert DuplicateDetector().find_duplicates(files) == []


def test_find_duplicates_does_not_mutate_shared_input_records(tmp_path):
    files = [
        _record(_write(tmp_path / "a.txt", b"duplicate")),
        _record(_write(tmp_path / "b.txt", b"duplicate")),
    ]
    snapshot = copy.deepcopy(files)

    groups = DuplicateDetector().find_duplicates(files)

    assert files == snapshot
    assert all("hash" not in item for item in files)
    assert all("hash" in item for item in groups[0]["files"])


def test_multiple_copies_calculate_total_and_savings(tmp_path):
    paths = [
        _write(tmp_path / "a.txt", b"123456"),
        _write(tmp_path / "b.txt", b"123456"),
        _write(tmp_path / "c.txt", b"123456"),
    ]
    groups = DuplicateDetector().find_duplicates([_record(p) for p in paths])

    assert groups[0]["count"] == 3
    assert groups[0]["total_size"] == 18
    assert groups[0]["potential_savings"] == 12


def test_pre_cancelled_detection_does_no_hashing(tmp_path, monkeypatch):
    first = _write(tmp_path / "a.txt", b"same")
    second = _write(tmp_path / "b.txt", b"same")
    detector = DuplicateDetector()
    event = threading.Event()
    event.set()

    def fail_hash(*args, **kwargs):
        raise AssertionError("hash should not be calculated after cancellation")

    monkeypatch.setattr(detector, "calculate_hash", fail_hash)

    result = detector.find_duplicates(
        [_record(first), _record(second)], cancel_event=event
    )

    assert result == []
    assert detector.cancelled is True


def test_cancel_during_hashing_returns_no_partial_groups(tmp_path):
    paths = []
    for index in range(4):
        paths.append(_write(tmp_path / f"{index}.txt", b"same"))

    detector = DuplicateDetector()
    progress = []

    def on_progress(item):
        progress.append(item)
        if item["files_hashed"] >= 1:
            detector.cancel()

    result = detector.find_duplicates(
        [_record(path) for path in paths], progress_callback=on_progress
    )

    assert detector.cancelled is True
    assert result == []
    assert len(progress) == 1


def test_hash_errors_are_reported_and_skipped(tmp_path):
    good = _write(tmp_path / "good.txt", b"same")
    missing_path = tmp_path / "missing.txt"
    missing = {
        "name": missing_path.name,
        "path": str(missing_path),
        "directory": str(missing_path.parent),
        "size": 4,
        "extension": ".txt",
        "is_file": True,
    }
    detector = DuplicateDetector()
    errors = []

    groups = detector.find_duplicates(
        [_record(good), missing], error_callback=errors.append
    )

    assert groups == []
    assert errors
    assert errors[0]["kind"] in {"permission", "os", "missing"}
    assert errors[0]["path"] == missing["path"]


def test_progress_reports_hash_counts(tmp_path):
    paths = [
        _write(tmp_path / "a.txt", b"0123456789"),
        _write(tmp_path / "b.txt", b"0123456789"),
        _write(tmp_path / "c.txt", b"0123456789"),
    ]
    progress = []

    groups = DuplicateDetector().find_duplicates(
        [_record(path) for path in paths], progress_callback=progress.append
    )

    assert len(groups) == 1
    assert progress
    final = progress[-1]
    assert final["files_hashed"] == 3
    assert final["total_files"] == 3
    assert final["bytes_hashed"] == 30
    assert "current_path" in final
    assert "elapsed_seconds" in final


def test_empty_files_are_skipped_and_symlinks_are_not_hashed(tmp_path):
    empty_a = _write(tmp_path / "empty-a.txt", b"")
    empty_b = _write(tmp_path / "empty-b.txt", b"")
    target = _write(tmp_path / "target.txt", b"same")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not available: {exc}")

    detector = DuplicateDetector()
    groups = detector.find_duplicates(
        [_record(empty_a), _record(empty_b), _record(target), _record(link)]
    )

    assert groups == []
    assert detector.calculate_hash(str(link)) is None
    assert len(detector.last_errors) == 2
    assert all(item["kind"] == "link" for item in detector.last_errors)
    assert all(item["path"] == str(link) for item in detector.last_errors)
