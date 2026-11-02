"""Tests for the file scanner, duplicate detector and cleanup safety guard."""
import os
import sys

import pytest

from panther.services.cleanup_manager import CleanupManager, is_protected_path
from panther.services.duplicate_detector import DuplicateDetector
from panther.services.file_scanner import FileScanner

needs_symlinks = pytest.mark.skipif(
    sys.platform == "win32", reason="creating symlinks needs elevated rights on Windows"
)


def _write(root, rel, data):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def test_scan_honours_max_depth(tmp_path):
    _write(tmp_path, "top.bin", b"a")
    _write(tmp_path, "l1/mid.bin", b"b")
    _write(tmp_path, "l1/l2/deep.bin", b"c")
    names = lambda depth: {f["name"] for f in FileScanner().scan_directory(str(tmp_path), max_depth=depth)}
    assert names(0) == {"top.bin"}
    assert names(1) == {"top.bin", "mid.bin"}
    assert names(2) == {"top.bin", "mid.bin", "deep.bin"}


def test_scan_skips_hidden_unless_requested(tmp_path):
    _write(tmp_path, ".secret", b"x")
    _write(tmp_path, ".cache/file.bin", b"y")
    _write(tmp_path, "visible.bin", b"z")
    scanner = FileScanner()
    assert {f["name"] for f in scanner.scan_directory(str(tmp_path))} == {"visible.bin"}
    assert len(scanner.scan_directory(str(tmp_path), include_hidden=True)) == 3


def test_scan_missing_root_returns_empty(tmp_path):
    assert FileScanner().scan_directory(str(tmp_path / "nope")) == []


@needs_symlinks
def test_scan_ignores_symlinked_files_and_dirs(tmp_path):
    real = _write(tmp_path, "real/report.bin", b"x" * 100)
    os.symlink(real, tmp_path / "real" / "link_to_report.bin")
    os.symlink(tmp_path / "real", tmp_path / "loop")  # would recurse forever if followed
    files = FileScanner().scan_directory(str(tmp_path))
    assert [f["name"] for f in files] == ["report.bin"]


def test_duplicates_are_content_verified(tmp_path):
    _write(tmp_path, "a/one.bin", b"x" * 5000)
    _write(tmp_path, "b/two.bin", b"x" * 5000)
    _write(tmp_path, "c/same_size_different.bin", b"y" * 5000)
    files = FileScanner().scan_directory(str(tmp_path))
    groups = DuplicateDetector().find_duplicates(files)
    assert len(groups) == 1
    assert groups[0]["count"] == 2
    assert groups[0]["potential_savings"] == 5000
    assert {os.path.basename(f["path"]) for f in groups[0]["files"]} == {"one.bin", "two.bin"}


def test_empty_files_are_never_duplicates(tmp_path):
    _write(tmp_path, "a.txt", b"")
    _write(tmp_path, "b.txt", b"")
    assert DuplicateDetector().find_duplicates(FileScanner().scan_directory(str(tmp_path))) == []


@pytest.mark.skipif(sys.platform == "win32", reason="os.link semantics differ in CI sandboxes")
def test_hardlinks_do_not_count_as_duplicates(tmp_path):
    original = _write(tmp_path, "a/report.bin", b"x" * 5000)
    os.link(original, tmp_path / "a" / "hardlink.bin")
    files = FileScanner().scan_directory(str(tmp_path))
    assert len(files) == 2
    # Two names for one on-disk file: nothing to reclaim, so no duplicate group.
    assert DuplicateDetector().find_duplicates(files) == []


def test_hardlink_not_counted_in_real_duplicate_savings(tmp_path):
    original = _write(tmp_path, "a/report.bin", b"x" * 5000)
    _write(tmp_path, "b/copy.bin", b"x" * 5000)
    os.link(original, tmp_path / "a" / "hardlink.bin")
    groups = DuplicateDetector().find_duplicates(FileScanner().scan_directory(str(tmp_path)))
    assert groups[0]["count"] == 2
    assert groups[0]["potential_savings"] == 5000


# --- cleanup safety -------------------------------------------------------

@pytest.fixture
def fake_windows_dirs(tmp_path, monkeypatch):
    windir = tmp_path / "Windows"
    program_files = tmp_path / "Program Files"
    for d in (windir, program_files):
        d.mkdir()
    monkeypatch.setenv("WINDIR", str(windir))
    monkeypatch.setenv("SystemRoot", str(windir))
    monkeypatch.setenv("ProgramFiles", str(program_files))
    for var in ("ProgramFiles(x86)", "ProgramW6432", "ProgramData"):
        monkeypatch.delenv(var, raising=False)
    return windir, program_files


def test_is_protected_path_covers_roots_and_children(fake_windows_dirs, tmp_path):
    windir, program_files = fake_windows_dirs
    assert is_protected_path(str(windir))
    assert is_protected_path(str(windir / "System32" / "kernel32.dll"))
    assert is_protected_path(str(program_files / "App" / "app.exe"))
    assert not is_protected_path(str(tmp_path / "Documents" / "notes.txt"))


def test_protected_check_is_not_fooled_by_prefix_or_dotdot(fake_windows_dirs, tmp_path):
    windir, _ = fake_windows_dirs
    assert not is_protected_path(str(tmp_path / "Windows.old" / "file.txt"))  # sibling, not child
    assert is_protected_path(str(tmp_path / "Documents" / ".." / "Windows" / "x.dll"))


@needs_symlinks
def test_protected_check_resolves_symlinks(fake_windows_dirs, tmp_path):
    windir, _ = fake_windows_dirs
    target = _write(windir, "System32/important.dll", b"q")
    link = tmp_path / "innocent.dll"
    os.symlink(target, link)
    assert is_protected_path(str(link))


def test_permanent_delete_refuses_protected_files(fake_windows_dirs):
    windir, _ = fake_windows_dirs
    victim = _write(windir, "System32/important.dll", b"q")
    manager = CleanupManager()
    result = manager.permanent_delete([victim])
    assert result["success"] is False
    assert result["deleted"] == 0 and result["failed"] == 1
    assert os.path.exists(victim)
    assert "Protected" in result["details"]["failed"][0][1]


def test_recycle_bin_refuses_protected_files(fake_windows_dirs):
    pytest.importorskip("send2trash")
    _, program_files = fake_windows_dirs
    victim = _write(program_files, "App/app.exe", b"q")
    result = CleanupManager().move_to_recycle_bin([victim])
    assert result["moved"] == 0 and result["failed"] == 1
    assert os.path.exists(victim)


def test_permanent_delete_allows_ordinary_files_and_audits(fake_windows_dirs, tmp_path):
    victim = _write(tmp_path, "Downloads/old.bin", b"q")
    manager = CleanupManager()
    result = manager.permanent_delete([victim])
    assert result["deleted"] == 1 and not os.path.exists(victim)
    assert manager.get_audit_log()[-1]["action"] == "permanent_delete"


def test_cleanup_reports_missing_files(fake_windows_dirs, tmp_path):
    result = CleanupManager().permanent_delete([str(tmp_path / "ghost.bin")])
    assert result["success"] is False and result["failed"] == 1
