"""Tests for the read-only directory browsing service."""

import os
import stat
import threading
from datetime import datetime

import pytest

from panther.services import directory_browser as browser_module
from panther.services.directory_browser import DirectoryBrowser


def _entry(result, name):
    return next(item for item in result["entries"] if item["name"] == name)


def test_lists_directories_and_files_with_metadata(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    target = tmp_path / "file.txt"
    target.write_bytes(b"hello")

    result = DirectoryBrowser().list_directory(str(tmp_path))

    assert result["error"] is None
    assert result["path"] == str(tmp_path)
    assert result["cancelled"] is False
    assert result["truncated"] is False

    folder_entry = _entry(result, "folder")
    assert folder_entry["type"] == "directory"
    assert folder_entry["is_dir"] is True
    assert folder_entry["is_file"] is False
    assert folder_entry["size"] is None

    file_entry = _entry(result, "file.txt")
    assert file_entry["type"] == "file"
    assert file_entry["is_file"] is True
    assert file_entry["size"] == 5
    assert file_entry["modified"] == datetime.fromtimestamp(
        target.stat().st_mtime
    ).strftime("%Y-%m-%d %H:%M:%S")
    assert file_entry["path"] == str(target)


def test_sorting_puts_directories_first_then_names(tmp_path):
    (tmp_path / "zeta.txt").write_text("z")
    (tmp_path / "Alpha.txt").write_text("a")
    (tmp_path / "beta_dir").mkdir()
    (tmp_path / "alpha_dir").mkdir()

    result = DirectoryBrowser().list_directory(str(tmp_path))

    assert [item["name"] for item in result["entries"]] == [
        "alpha_dir",
        "beta_dir",
        "Alpha.txt",
        "zeta.txt",
    ]


def test_hidden_entries_are_included_and_marked(tmp_path):
    (tmp_path / ".hidden.txt").write_text("x")
    (tmp_path / ".hidden_dir").mkdir()

    result = DirectoryBrowser().list_directory(str(tmp_path))

    assert _entry(result, ".hidden.txt")["is_hidden"] is True
    assert _entry(result, ".hidden_dir")["is_hidden"] is True


def test_missing_directory_returns_error(tmp_path):
    missing = tmp_path / "missing"

    result = DirectoryBrowser().list_directory(str(missing))

    assert result["entries"] == []
    assert result["error"]["kind"] == "missing"
    assert result["path"] == str(missing)


def test_permission_denied_directory_is_reported(monkeypatch, tmp_path):
    def denied(path):
        raise PermissionError("denied by test")

    monkeypatch.setattr(browser_module.os, "scandir", denied)

    result = DirectoryBrowser().list_directory(str(tmp_path))

    assert result["entries"] == []
    assert result["error"]["kind"] == "permission"
    assert "denied" in result["error"]["error"].lower()


def test_disappearing_entry_is_skipped(monkeypatch, tmp_path):
    good = tmp_path / "good.txt"
    bad = tmp_path / "bad.txt"
    good.write_text("good")
    bad.write_text("bad")
    real_lstat = os.lstat

    def disappearing(path):
        if os.fspath(path) == str(bad):
            raise FileNotFoundError("vanished")
        return real_lstat(path)

    monkeypatch.setattr(browser_module.os, "lstat", disappearing)

    result = DirectoryBrowser().list_directory(str(tmp_path))

    assert [item["name"] for item in result["entries"]] == ["good.txt"]
    assert len(result["errors"]) == 1
    assert result["errors"][0]["path"] == str(bad)
    assert result["errors"][0]["kind"] == "missing"


def test_symlink_is_marked_and_not_traversed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    root = tmp_path / "root"
    root.mkdir()
    (root / "visible.txt").write_text("visible")
    link = root / "outside-link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not available: {exc}")

    result = DirectoryBrowser().list_directory(str(root))

    link_entry = _entry(result, "outside-link")
    assert link_entry["type"] == "link"
    assert link_entry["is_link"] is True
    assert link_entry["is_reparse"] is False
    assert {item["name"] for item in result["entries"]} == {
        "outside-link",
        "visible.txt",
    }


def test_reparse_point_simulation_is_marked(monkeypatch, tmp_path):
    target = tmp_path / "reparse-entry"
    target.mkdir()

    class FakeStat:
        st_mode = stat.S_IFDIR | 0o700
        st_file_attributes = 0x400
        st_size = 0
        st_mtime = 0
        st_ctime = 0

    real_lstat = os.lstat

    def fake_lstat(path):
        if os.fspath(path) == str(target):
            return FakeStat()
        return real_lstat(path)

    monkeypatch.setattr(browser_module.os, "lstat", fake_lstat)

    result = DirectoryBrowser().list_directory(str(tmp_path))

    entry = _entry(result, "reparse-entry")
    assert entry["type"] == "reparse"
    assert entry["is_reparse"] is True
    assert entry["is_link"] is False


def test_large_directory_listing_is_bounded(tmp_path):
    for index in range(8):
        (tmp_path / f"file-{index}.txt").write_text(str(index))

    result = DirectoryBrowser(limit=3).list_directory(str(tmp_path))

    assert len(result["entries"]) == 3
    assert result["limit"] == 3
    assert result["truncated"] is True


def test_pre_cancelled_listing_returns_no_entries(tmp_path):
    (tmp_path / "file.txt").write_text("x")
    event = threading.Event()
    event.set()

    result = DirectoryBrowser().list_directory(
        str(tmp_path), cancel_event=event
    )

    assert result["cancelled"] is True
    assert result["entries"] == []
