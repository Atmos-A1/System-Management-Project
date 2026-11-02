"""Tests for bounded, read-only file-signature inspection."""

import os
import stat

import pytest

from panther.services import file_signature as signature_module
from panther.services.file_signature import (
    MAX_SIGNATURE_BYTES,
    FileSignatureInspector,
)


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class FakeStat:
    def __init__(
        self,
        mode=stat.S_IFREG | 0o644,
        size=0,
        attributes=None,
        inode=1234,
        device=1,
    ):
        self.st_mode = mode
        self.st_size = size
        self.st_ino = inode
        self.st_dev = device
        self.st_nlink = 1
        if attributes is not None:
            self.st_file_attributes = attributes


@pytest.mark.parametrize(
    "name,payload,expected_format",
    [
        ("sample.pdf", b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n", "PDF"),
        (
            "sample.png",
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 12,
            "PNG",
        ),
        (
            "sample.jpg",
            b"\xff\xd8\xff\xe0" + b"\x00" * 12,
            "JPEG",
        ),
        ("sample.gif", b"GIF89a" + b"\x00" * 12, "GIF"),
        ("sample.zip", b"PK\x03\x04" + b"\x00" * 12, "ZIP"),
        ("sample.gz", b"\x1f\x8b\x08" + b"\x00" * 12, "GZIP"),
        ("sample.elf", b"\x7fELF\x02\x01\x01" + b"\x00" * 8, "ELF"),
        ("sample.exe", b"MZ\x90\x00" + b"\x00" * 12, "PE"),
        ("sample.mp3", b"ID3\x04\x00\x00" + b"\x00" * 12, "MP3"),
        (
            "sample.wav",
            b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + b"\x00" * 12,
            "WAV",
        ),
    ],
)
def test_recognized_signatures(tmp_path, name, payload, expected_format):
    target = _write(tmp_path / name, payload + b"\x00" * 100)

    result = FileSignatureInspector().inspect(str(target))

    assert result["ok"] is True
    assert result["status"] == "recognized"
    assert result["format"] == expected_format
    assert result["extension_match"] == "match"
    assert result["bytes_read"] <= MAX_SIGNATURE_BYTES
    assert result["error"] == ""


def test_unknown_signature(tmp_path):
    target = _write(tmp_path / "blob.bin", b"not-a-known-signature")

    result = FileSignatureInspector().inspect(str(target))

    assert result["ok"] is True
    assert result["status"] == "unknown"
    assert result["format"] is None
    assert result["extension_match"] == "unknown"


def test_empty_file_is_reported(tmp_path):
    target = _write(tmp_path / "empty.pdf", b"")

    result = FileSignatureInspector().inspect(str(target))

    assert result["ok"] is True
    assert result["status"] == "empty"
    assert result["format"] is None
    assert result["bytes_read"] == 0
    assert result["extension_match"] == "unknown"


def test_unreadable_file_is_reported(monkeypatch, tmp_path):
    target = _write(tmp_path / "blocked.pdf", b"%PDF-1.7")

    def denied(_path, _flags):
        raise PermissionError("denied by test")

    monkeypatch.setattr(signature_module.os, "open", denied)

    result = FileSignatureInspector().inspect(str(target))

    assert result["ok"] is False
    assert result["status"] == "unreadable"
    assert result["error_kind"] == "permission"
    assert "denied" in result["error"].lower()


def test_directory_is_unsupported(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()

    result = FileSignatureInspector().inspect(str(folder))

    assert result["ok"] is False
    assert result["status"] == "unsupported"
    assert result["entry_type"] == "directory"
    assert result["format"] is None


def test_symlink_is_rejected_without_opening(monkeypatch, tmp_path):
    outside = _write(tmp_path / "outside" / "secret.bin", b"%PDF-1.7")
    link = tmp_path / "link.pdf"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not available: {exc}")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("must not open a symbolic link")

    monkeypatch.setattr(signature_module.os, "open", forbidden)

    result = FileSignatureInspector().inspect(str(link))

    assert result["ok"] is False
    assert result["status"] == "unsupported"
    assert result["entry_type"] == "link"
    assert result["error_kind"] == "link"


def test_reparse_point_is_rejected(monkeypatch, tmp_path):
    target = tmp_path / "junction.pdf"
    _write(target, b"%PDF-1.7")
    fake = FakeStat(
        mode=stat.S_IFREG | 0o644,
        size=8,
        attributes=0x400,
    )
    real_lstat = os.lstat

    def fake_lstat(path):
        if os.fspath(path) == str(target):
            return fake
        return real_lstat(path)

    monkeypatch.setattr(signature_module.os, "lstat", fake_lstat)

    result = FileSignatureInspector().inspect(str(target))

    assert result["ok"] is False
    assert result["status"] == "unsupported"
    assert result["entry_type"] == "reparse"
    assert result["error_kind"] == "reparse"


def test_extension_mismatch_is_informational(tmp_path):
    target = _write(
        tmp_path / "not-really.txt", b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    )

    result = FileSignatureInspector().inspect(str(target))

    assert result["status"] == "recognized"
    assert result["format"] == "PNG"
    assert result["extension"] == ".txt"
    assert result["extension_match"] == "mismatch"


def test_extensionless_file_has_no_extension_conclusion(tmp_path):
    target = _write(
        tmp_path / "payload", b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    )

    result = FileSignatureInspector().inspect(str(target))

    assert result["status"] == "recognized"
    assert result["format"] == "PNG"
    assert result["extension"] == ""
    assert result["extension_match"] == "unavailable"


def test_file_changed_during_inspection(monkeypatch, tmp_path):
    target = _write(tmp_path / "changing.pdf", b"%PDF-1.7")
    real_fstat = os.fstat

    def changed(fd):
        opened = real_fstat(fd)
        published = FakeStat(
            mode=opened.st_mode,
            size=opened.st_size,
            inode=opened.st_ino + 1,
            device=opened.st_dev,
        )
        return published

    monkeypatch.setattr(signature_module.os, "fstat", changed)

    result = FileSignatureInspector().inspect(str(target))

    assert result["ok"] is False
    assert result["status"] == "changed"
    assert result["format"] is None
    assert "changed" in result["error"].lower()


def test_file_disappears_between_lstat_and_open(monkeypatch, tmp_path):
    target = _write(tmp_path / "vanishing.pdf", b"%PDF-1.7")

    def vanished(_path, _flags):
        raise FileNotFoundError("vanished")

    monkeypatch.setattr(signature_module.os, "open", vanished)

    result = FileSignatureInspector().inspect(str(target))

    assert result["ok"] is False
    assert result["status"] == "changed"
    assert result["error_kind"] == "missing"


def test_read_is_bounded(monkeypatch, tmp_path):
    target = _write(tmp_path / "large.bin", b"A" * (1024 * 1024))
    requested = []
    real_read = os.read

    def tracking_read(fd, size):
        requested.append(size)
        return real_read(fd, size)

    monkeypatch.setattr(signature_module.os, "read", tracking_read)

    result = FileSignatureInspector().inspect(str(target))

    assert MAX_SIGNATURE_BYTES == 64
    assert result["bytes_read"] == MAX_SIGNATURE_BYTES
    assert requested
    assert max(requested) <= MAX_SIGNATURE_BYTES


@pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW"), reason="O_NOFOLLOW unavailable"
)
def test_open_uses_no_follow_flag(monkeypatch, tmp_path):
    target = _write(tmp_path / "sample.pdf", b"%PDF-1.7")
    seen = []
    real_open = os.open

    def tracking_open(path, flags, *args, **kwargs):
        seen.append(flags)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(signature_module.os, "open", tracking_open)

    result = FileSignatureInspector().inspect(str(target))

    assert result["status"] == "recognized"
    assert seen
    assert seen[0] & os.O_NOFOLLOW
    assert result["no_follow_supported"] is True


def test_file_descriptor_is_closed(monkeypatch, tmp_path):
    target = _write(tmp_path / "sample.pdf", b"%PDF-1.7")
    opened = []
    real_open = os.open

    def tracking_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(signature_module.os, "open", tracking_open)

    result = FileSignatureInspector().inspect(str(target))

    assert result["status"] == "recognized"
    assert opened
    with pytest.raises(OSError):
        os.fstat(opened[0])
