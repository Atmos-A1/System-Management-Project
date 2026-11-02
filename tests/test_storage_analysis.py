"""Tests for folder-size and file-type storage analysis."""

import os
import stat
import threading

import pytest

from panther.services import storage_analysis as analysis_module
from panther.services.storage_analysis import StorageAnalysis


def _write(path, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _folder(result, name):
    return next(item for item in result["folders"] if item["name"] == name)


def _type(result, key):
    return next(item for item in result["file_types"] if item["key"] == key)


def test_folder_sizes_include_nested_files_and_root_files(tmp_path):
    _write(tmp_path / "alpha" / "a.bin", b"123")
    _write(tmp_path / "alpha" / "sub" / "b.bin", b"1234567")
    _write(tmp_path / "beta" / "c.bin", b"12345")
    _write(tmp_path / "root.txt", b"12")

    result = StorageAnalysis().analyze([str(tmp_path)])

    assert result["status"] == "complete"
    assert result["total_size"] == 17
    assert result["file_count"] == 4
    assert [item["name"] for item in result["folders"]] == ["alpha", "beta"]

    alpha = _folder(result, "alpha")
    assert alpha["size"] == 10
    assert alpha["file_count"] == 2
    assert alpha["directory_count"] == 2
    assert alpha["status"] == "complete"

    beta = _folder(result, "beta")
    assert beta["size"] == 5

    assert result["root_summaries"][0]["direct_size"] == 2
    assert result["root_summaries"][0]["direct_file_count"] == 1


def test_multiple_roots_are_combined(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write(first / "one" / "a.bin", b"12")
    _write(second / "two" / "b.bin", b"345")

    result = StorageAnalysis().analyze([str(first), str(second)])

    assert result["status"] == "complete"
    assert result["total_size"] == 5
    assert result["file_count"] == 2
    assert len(result["root_summaries"]) == 2
    assert {item["root"] for item in result["folders"]} == {
        str(first),
        str(second),
    }
    assert {item["name"]: item["size"] for item in result["folders"]} == {
        "one": 2,
        "two": 3,
    }


def test_empty_directory_and_zero_byte_files_are_safe(tmp_path):
    (tmp_path / "empty").mkdir()
    _write(tmp_path / "zero.txt", b"")

    result = StorageAnalysis().analyze([str(tmp_path)])

    assert result["status"] == "complete"
    assert result["total_size"] == 0
    assert result["file_count"] == 1
    empty = _folder(result, "empty")
    assert empty["size"] == 0
    assert empty["status"] == "complete"
    assert _type(result, ".txt")["size"] == 0
    assert _type(result, ".txt")["percentage"] == 0.0


def test_file_types_are_normalised_and_percentages_are_calculated(tmp_path):
    _write(tmp_path / "a.PDF", b"123")
    _write(tmp_path / "b.pdf", b"12345")
    _write(tmp_path / "no-extension", b"12")
    _write(tmp_path / "zero.docx", b"")
    _write(tmp_path / "sub" / "photo.JPG", b"1234")

    result = StorageAnalysis().analyze([str(tmp_path)])

    pdf = _type(result, ".pdf")
    assert pdf["count"] == 2
    assert pdf["size"] == 8
    assert pdf["percentage"] == pytest.approx(8 / 14 * 100)

    extensionless = _type(result, "")
    assert extensionless["label"] == "No extension"
    assert extensionless["count"] == 1
    assert extensionless["size"] == 2

    assert _type(result, ".docx")["count"] == 1
    assert _type(result, ".docx")["size"] == 0
    assert _type(result, ".docx")["percentage"] == 0.0
    assert _type(result, ".jpg")["size"] == 4
    assert sum(item["percentage"] for item in result["file_types"]) == (
        pytest.approx(100.0)
    )


def test_empty_root_has_no_file_types(tmp_path):
    result = StorageAnalysis().analyze([str(tmp_path)])

    assert result["status"] == "complete"
    assert result["total_size"] == 0
    assert result["file_types"] == []


def test_permission_denied_directory_marks_partial(monkeypatch, tmp_path):
    _write(tmp_path / "good" / "a.bin", b"123")
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    _write(blocked / "hidden.bin", b"123456")
    real_scandir = os.scandir

    def fake_scandir(path):
        if os.fspath(path) == str(blocked):
            raise PermissionError("denied by test")
        return real_scandir(path)

    monkeypatch.setattr(analysis_module.os, "scandir", fake_scandir)

    result = StorageAnalysis().analyze([str(tmp_path)])

    assert result["status"] == "partial"
    assert result["partial"] is True
    assert result["skipped_count"] == 1
    assert result["total_size"] == 3
    assert _folder(result, "blocked")["status"] == "partial"
    assert result["errors"][0]["path"] == str(blocked)


def test_disappearing_file_is_skipped_and_reported(monkeypatch, tmp_path):
    good = _write(tmp_path / "good.txt", b"123")
    bad = _write(tmp_path / "bad.txt", b"456")
    real_lstat = os.lstat

    def fake_lstat(path):
        if os.fspath(path) == str(bad):
            raise FileNotFoundError("vanished")
        return real_lstat(path)

    monkeypatch.setattr(analysis_module.os, "lstat", fake_lstat)

    result = StorageAnalysis().analyze([str(tmp_path)])

    assert result["status"] == "partial"
    assert result["total_size"] == 3
    assert result["file_count"] == 1
    assert result["skipped_count"] == 1
    assert result["errors"][0]["path"] == str(bad)


def test_error_list_is_bounded(monkeypatch, tmp_path):
    for index in range(8):
        _write(tmp_path / f"file-{index}.txt", b"x")
    real_lstat = os.lstat

    def fake_lstat(path):
        if os.fspath(path).endswith(".txt"):
            raise FileNotFoundError("vanished")
        return real_lstat(path)

    monkeypatch.setattr(analysis_module.os, "lstat", fake_lstat)

    result = StorageAnalysis(max_errors=2).analyze([str(tmp_path)])

    assert result["skipped_count"] == 8
    assert len(result["errors"]) == 2
    assert result["status"] == "partial"


def test_symlinks_and_reparse_points_are_excluded(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    _write(outside / "secret.bin", b"123456")
    root = tmp_path / "root"
    _write(root / "visible.bin", b"123")
    link = root / "outside-link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not available: {exc}")

    result = StorageAnalysis().analyze([str(root)])

    assert result["total_size"] == 3
    assert result["excluded_links"] == 1
    assert [item["name"] for item in result["folders"]] == []

    reparse_root = tmp_path / "reparse-root"
    reparse_root.mkdir()
    reparse_dir = reparse_root / "junction"
    reparse_dir.mkdir()
    _write(reparse_dir / "secret.bin", b"999")

    class FakeStat:
        st_mode = stat.S_IFDIR | 0o700
        st_file_attributes = 0x400
        st_size = 0
        st_mtime = 0
        st_dev = 0
        st_ino = 0
        st_nlink = 1

    real_lstat = os.lstat

    def fake_lstat(path):
        if os.fspath(path) == str(reparse_dir):
            return FakeStat()
        return real_lstat(path)

    monkeypatch.setattr(analysis_module.os, "lstat", fake_lstat)

    reparse_result = StorageAnalysis().analyze([str(reparse_root)])

    assert reparse_result["total_size"] == 0
    assert reparse_result["excluded_links"] == 1


def test_hard_linked_files_are_counted_once(tmp_path):
    first = _write(tmp_path / "first.bin", b"12345")
    second = tmp_path / "second.bin"
    try:
        os.link(first, second)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"hard links not available: {exc}")

    result = StorageAnalysis().analyze([str(tmp_path)])

    assert result["total_size"] == 5
    assert result["file_count"] == 1
    assert _type(result, ".bin")["count"] == 1


def test_cancellation_and_progress_are_reported(tmp_path):
    for index in range(20):
        _write(tmp_path / f"file-{index}.bin", b"123")
    event = threading.Event()
    progress = []

    def on_progress(item):
        progress.append(item)
        if item["files_scanned"] >= 1:
            event.set()

    result = StorageAnalysis().analyze(
        [str(tmp_path)],
        cancel_event=event,
        progress_callback=on_progress,
    )

    assert result["cancelled"] is True
    assert result["status"] == "cancelled"
    assert result["total_size"] >= 3
    assert progress
    assert {
        "files_scanned",
        "directories_scanned",
        "bytes_scanned",
        "current_path",
        "elapsed_seconds",
    }.issubset(progress[0])


def test_missing_roots_fail_safely(tmp_path):
    result = StorageAnalysis().analyze(
        [str(tmp_path / "missing")]
    )

    assert result["status"] == "failed"
    assert result["failed"] is True
    assert result["file_types"] == []
    assert result["errors"]


def test_file_type_aggregation_is_bounded(tmp_path):
    _write(tmp_path / "a.aaa", b"1")
    _write(tmp_path / "b.bbb", b"1")
    _write(tmp_path / "c.ccc", b"1")

    result = StorageAnalysis(max_file_types=2).analyze([str(tmp_path)])

    assert result["file_count"] == 3
    assert len(result["file_types"]) == 3
    assert any(item["label"] == "Other" for item in result["file_types"])


def test_large_directory_does_not_return_a_file_list(tmp_path):
    for index in range(300):
        _write(tmp_path / "many" / f"file-{index}.txt", b"x")

    result = StorageAnalysis().analyze([str(tmp_path)])

    assert result["file_count"] == 300
    assert result["total_size"] == 300
    assert "files" not in result
    assert len(result["folders"]) == 1
    assert result["folders"][0]["file_count"] == 300
