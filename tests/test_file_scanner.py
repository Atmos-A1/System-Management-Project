"""Tests for the filesystem scanner foundation."""

import os
import stat as stat_module
import threading
from datetime import datetime
from pathlib import Path

import pytest

from panther.services.file_scanner import FileScanner, _is_reparse_point


def _write(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _names(files):
    return {item["name"] for item in files}


def test_max_depth_boundary_is_exact(tmp_path):
    _write(tmp_path / "root.txt")
    _write(tmp_path / "one" / "one.txt")
    _write(tmp_path / "one" / "two" / "two.txt")
    _write(tmp_path / "one" / "two" / "three" / "three.txt")

    scanner = FileScanner()

    assert _names(scanner.scan_directory(str(tmp_path), max_depth=0)) == {"root.txt"}
    assert _names(scanner.scan_directory(str(tmp_path), max_depth=1)) == {
        "root.txt",
        "one.txt",
    }
    assert _names(scanner.scan_directory(str(tmp_path), max_depth=2)) == {
        "root.txt",
        "one.txt",
        "two.txt",
    }
    assert _names(scanner.scan_directory(str(tmp_path), max_depth=3)) == {
        "root.txt",
        "one.txt",
        "two.txt",
        "three.txt",
    }


def test_nested_directories_and_metadata(tmp_path):
    target = _write(tmp_path / "docs" / "report.txt", b"hello")

    files = FileScanner().scan_directory(str(tmp_path), max_depth=5)

    assert len(files) == 1
    item = files[0]
    assert item["name"] == "report.txt"
    assert item["path"] == str(target)
    assert item["directory"] == str(target.parent)
    assert item["size"] == 5
    assert item["extension"] == ".txt"
    assert item["is_file"] is True
    assert item["created"] == datetime.fromtimestamp(
        target.stat().st_ctime
    ).strftime("%Y-%m-%d %H:%M:%S")
    assert item["modified"] == datetime.fromtimestamp(
        target.stat().st_mtime
    ).strftime("%Y-%m-%d %H:%M:%S")


def test_missing_root_is_reported(tmp_path):
    scanner = FileScanner()
    errors = []

    result = scanner.scan_directory(
        str(tmp_path / "does-not-exist"),
        error_callback=errors.append,
    )

    assert result == []
    assert len(scanner.last_errors) == 1
    assert scanner.last_errors[0]["kind"] == "missing"
    assert errors == scanner.last_errors


def test_root_that_is_a_file_is_reported(tmp_path):
    file_path = _write(tmp_path / "single.txt")
    scanner = FileScanner()

    result = scanner.scan_directory(str(file_path))

    assert result == []
    assert scanner.last_errors[0]["kind"] == "not_directory"


def test_inaccessible_file_is_reported_and_scan_continues(tmp_path, monkeypatch):
    good = _write(tmp_path / "good.txt")
    bad = _write(tmp_path / "bad.txt")
    real_stat = os.stat
    errors = []

    def fake_stat(path, *args, **kwargs):
        if os.fspath(path) == str(bad):
            raise PermissionError("denied by test")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", fake_stat)

    files = FileScanner().scan_directory(
        str(tmp_path), error_callback=errors.append
    )

    assert _names(files) == {"good.txt"}
    assert good.name in {item["name"] for item in files}
    assert len(errors) == 1
    assert errors[0]["path"] == str(bad)
    assert errors[0]["kind"] == "permission"


def test_inaccessible_directory_is_reported_and_scan_continues(
    tmp_path, monkeypatch
):
    _write(tmp_path / "visible.txt")
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    _write(blocked / "inside.txt")
    real_scandir = os.scandir
    errors = []

    def fake_scandir(path):
        if os.fspath(path) == str(blocked):
            raise PermissionError(13, "denied by test", str(blocked))
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", fake_scandir)

    files = FileScanner().scan_directory(
        str(tmp_path), max_depth=3, error_callback=errors.append
    )

    assert _names(files) == {"visible.txt"}
    assert len(errors) == 1
    assert errors[0]["path"] == str(blocked)
    assert errors[0]["kind"] == "permission"


def test_pre_cancelled_scan_returns_no_files(tmp_path):
    _write(tmp_path / "a.txt")
    event = threading.Event()
    event.set()
    scanner = FileScanner()

    result = scanner.scan_directory(str(tmp_path), cancel_event=event)

    assert result == []
    assert scanner.cancelled is True


def test_cancel_from_progress_callback_stops_scan(tmp_path):
    for index in range(5):
        _write(tmp_path / f"{index}.txt")
    scanner = FileScanner()
    seen = []

    def on_progress(progress):
        seen.append(progress["files_scanned"])
        if progress["files_scanned"] >= 1:
            scanner.cancel()

    result = scanner.scan_directory(str(tmp_path), progress_callback=on_progress)

    assert scanner.cancelled is True
    assert len(result) == 1
    assert seen == [1]


def test_progress_reports_counts_bytes_and_current_path(tmp_path):
    _write(tmp_path / "a.txt", b"abc")
    _write(tmp_path / "sub" / "b.txt", b"12345")
    progress = []

    files = FileScanner().scan_directory(
        str(tmp_path), max_depth=2, progress_callback=progress.append
    )

    assert len(files) == 2
    assert progress
    final = progress[-1]
    assert final["files_scanned"] == 2
    assert final["directories_scanned"] >= 2
    assert final["bytes_scanned"] == 8
    assert "current_path" in final
    assert "elapsed_seconds" in final


def test_hidden_files_and_directories_are_excluded_by_default(tmp_path):
    _write(tmp_path / "visible.txt")
    _write(tmp_path / ".hidden.txt")
    _write(tmp_path / ".hidden_dir" / "inside.txt")
    _write(tmp_path / "visible_dir" / "inside.txt")

    scanner = FileScanner()
    default = scanner.scan_directory(str(tmp_path), max_depth=3)
    included = scanner.scan_directory(
        str(tmp_path), max_depth=3, include_hidden=True
    )

    assert _names(default) == {"visible.txt", "inside.txt"}
    assert _names(included) == {
        "visible.txt",
        ".hidden.txt",
        "inside.txt",
    }
    assert sum(1 for item in included if item["name"] == "inside.txt") == 2


def test_symlinks_are_not_traversed_or_returned(tmp_path):
    outside = tmp_path / "outside"
    secret = _write(outside / "secret.txt")
    root = tmp_path / "root"
    _write(root / "regular.txt")
    try:
        (root / "link.txt").symlink_to(secret)
        (root / "linkdir").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not available: {exc}")

    files = FileScanner().scan_directory(str(root), max_depth=5)

    assert _names(files) == {"regular.txt"}
    assert [item["path"] for item in files] == [str(root / "regular.txt")]


def test_reparse_point_flag_is_recognised():
    flag = getattr(stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

    class FakeStat:
        st_file_attributes = flag

    assert _is_reparse_point(FakeStat()) is True
    assert _is_reparse_point(object()) is False


def test_get_largest_files_keeps_existing_behaviour():
    files = [{"name": "a", "size": 1}, {"name": "b", "size": 5}]

    result = FileScanner().get_largest_files(files, limit=1)

    assert result == [{"name": "b", "size": 5}]
