"""Tests for safe, read-only filesystem metadata inspection."""

import os
import stat
from datetime import datetime

import pytest

from panther.services import file_metadata as metadata_module
from panther.services.file_metadata import FileMetadataInspector


def _write(path, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class FakeStat:
    def __init__(
        self,
        mode=stat.S_IFREG | 0o644,
        size=0,
        mtime=0,
        atime=0,
        ctime=0,
        attributes=None,
        inode=1234,
        device=1,
        links=1,
    ):
        self.st_mode = mode
        self.st_size = size
        self.st_mtime = mtime
        self.st_atime = atime
        self.st_ctime = ctime
        self.st_ino = inode
        self.st_dev = device
        self.st_nlink = links
        if attributes is not None:
            self.st_file_attributes = attributes


def test_regular_file_metadata(tmp_path):
    target = _write(tmp_path / "report.txt", b"hello")
    os.utime(target, (1_600_000_000, 1_600_000_500))

    result = FileMetadataInspector().inspect(str(target))

    assert result["ok"] is True
    assert result["entry_type"] == "file"
    assert result["name"] == "report.txt"
    assert result["path"] == str(target)
    assert result["extension"] == ".txt"
    assert result["size"] == 5
    assert result["classification"] == "Text file"
    assert result["modified"] == datetime.fromtimestamp(
        1_600_000_500
    ).strftime("%Y-%m-%d %H:%M:%S")
    assert result["accessed"] == datetime.fromtimestamp(
        1_600_000_000
    ).strftime("%Y-%m-%d %H:%M:%S")
    assert result["is_hidden"] is False
    assert result["is_read_only"] is False
    assert result["is_link"] is False
    assert result["is_reparse"] is False
    assert result["is_file"] is True
    assert result["is_dir"] is False
    assert result["error"] == ""


def test_directory_metadata(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()

    result = FileMetadataInspector().inspect(str(folder))

    assert result["ok"] is True
    assert result["entry_type"] == "directory"
    assert result["classification"] == "Folder"
    assert result["size"] is None
    assert result["is_dir"] is True
    assert result["is_file"] is False
    assert result["modified"]
    assert result["accessed"]


def test_hidden_file_is_marked(tmp_path):
    target = _write(tmp_path / ".secret", b"x")

    result = FileMetadataInspector().inspect(str(target))

    assert result["is_hidden"] is True


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode-bit semantics")
def test_read_only_file_is_marked(tmp_path):
    target = _write(tmp_path / "locked.txt", b"x")
    target.chmod(0o444)
    try:
        result = FileMetadataInspector().inspect(str(target))
        assert result["is_read_only"] is True
    finally:
        target.chmod(0o644)


def test_missing_file_is_reported(tmp_path):
    missing = tmp_path / "missing.txt"

    result = FileMetadataInspector().inspect(str(missing))

    assert result["ok"] is False
    assert result["error_kind"] == "missing"
    assert result["entry_type"] is None
    assert result["size"] is None
    assert "missing" in result["error"].lower()


def test_permission_error_is_reported(monkeypatch, tmp_path):
    target = _write(tmp_path / "protected.txt", b"x")
    real_lstat = os.lstat

    def denied(path):
        if os.fspath(path) == str(target):
            raise PermissionError("denied by test")
        return real_lstat(path)

    monkeypatch.setattr(metadata_module.os, "lstat", denied)

    result = FileMetadataInspector().inspect(str(target))

    assert result["ok"] is False
    assert result["error_kind"] == "permission"
    assert "denied" in result["error"].lower()


def test_disappearing_file_is_reported(monkeypatch, tmp_path):
    target = _write(tmp_path / "vanishing.txt", b"x")
    real_lstat = os.lstat

    def vanished(path):
        if os.fspath(path) == str(target):
            raise FileNotFoundError("vanished")
        return real_lstat(path)

    monkeypatch.setattr(metadata_module.os, "lstat", vanished)

    result = FileMetadataInspector().inspect(str(target))

    assert result["ok"] is False
    assert result["error_kind"] == "missing"


def test_symlink_is_rejected_without_reading_target(tmp_path):
    outside = _write(tmp_path / "outside" / "secret.bin", b"secret")
    link = tmp_path / "link"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not available: {exc}")

    result = FileMetadataInspector().inspect(str(link))

    assert result["ok"] is False
    assert result["entry_type"] == "link"
    assert result["is_link"] is True
    assert result["error_kind"] == "link"
    assert result["size"] is None
    assert "symbolic link" in result["error"].lower()


def test_reparse_point_is_rejected(monkeypatch, tmp_path):
    target = tmp_path / "junction"
    target.mkdir()
    fake = FakeStat(
        mode=stat.S_IFDIR | 0o700,
        attributes=0x400,
        size=0,
    )
    real_lstat = os.lstat

    def fake_lstat(path):
        if os.fspath(path) == str(target):
            return fake
        return real_lstat(path)

    monkeypatch.setattr(metadata_module.os, "lstat", fake_lstat)

    result = FileMetadataInspector().inspect(str(target))

    assert result["ok"] is False
    assert result["entry_type"] == "reparse"
    assert result["is_reparse"] is True
    assert result["error_kind"] == "reparse"


def test_creation_time_is_not_invented_without_birthtime(
    monkeypatch, tmp_path
):
    target = _write(tmp_path / "file.bin", b"x")
    fake = FakeStat(mtime=100, atime=200, ctime=300)
    monkeypatch.setattr(
        metadata_module.os, "lstat", lambda _path: fake
    )
    monkeypatch.setattr(metadata_module.os, "name", "posix")

    result = FileMetadataInspector().inspect(str(target))

    assert result["ok"] is True
    assert result["created"] is None
    assert result["created_available"] is False


def test_attributes_are_unavailable_without_platform_attributes(
    monkeypatch, tmp_path
):
    target = _write(tmp_path / "file.bin", b"x")
    fake = FakeStat()
    monkeypatch.setattr(
        metadata_module.os, "lstat", lambda _path: fake
    )
    monkeypatch.setattr(metadata_module.os, "name", "posix")

    result = FileMetadataInspector().inspect(str(target))

    assert result["attributes"] == []
    assert result["attributes_supported"] is False


def test_inspection_uses_lstat_not_stat(monkeypatch, tmp_path):
    target = _write(tmp_path / "file.bin", b"x")
    real_stat = os.stat

    def forbidden(path, *args, **kwargs):
        if os.fspath(path) == str(target):
            raise AssertionError("metadata inspection must not follow links")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(metadata_module.os, "stat", forbidden)

    result = FileMetadataInspector().inspect(str(target))

    assert result["ok"] is True
    assert result["size"] == 1
