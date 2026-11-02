"""Tests for cleanup path policy and filesystem preflight."""

import os
import stat
from pathlib import Path

import pytest

from panther.services.cleanup_policy import (
    inspect_path,
    inspect_paths,
    is_protected_path,
    is_within,
    path_rejection_reason,
)

WINDOWS_ENV = {
    "SystemDrive": "C:",
    "SystemRoot": r"C:\Windows",
    "ProgramFiles": r"C:\Program Files",
    "ProgramFiles(x86)": r"C:\Program Files (x86)",
    "ProgramData": r"C:\ProgramData",
    "USERPROFILE": r"C:\Users\me",
}


def test_component_aware_windows_comparison():
    root = r"C:\Users\me\Downloads"
    assert is_within(r"C:\USERS\ME\DOWNLOADS\sub\a.txt", root, windows=True)
    assert is_within(
        "C:/Users/me/Downloads/sub/a.txt", root, windows=True
    )
    assert not is_within(
        r"C:\Users\me\Downloads2\a.txt", root, windows=True
    )
    assert not is_within(
        r"C:\Users\me\Downloads\..\Secrets\a.txt", root, windows=True
    )


def test_unc_and_mixed_separator_comparison():
    root = r"\\Server\Share\Folder"
    assert is_within(
        "//server/share/folder/sub/a.txt", root, windows=True
    )
    assert not is_within(
        r"\\Server\Share\Folder2\a.txt", root, windows=True
    )


def test_windows_protected_system_and_application_paths():
    for path in [
        r"C:\Windows\System32\cmd.exe",
        r"C:\WINDOWS\SysWOW64\file.dll",
        r"C:\Program Files\Some App\cache.tmp",
        r"C:\Program Files (x86)\Some App\cache.tmp",
        r"C:\ProgramData\Some App\data.bin",
        r"C:\Users\me\AppData\Local\Some App\cache.bin",
        r"C:\$Recycle.Bin\file.txt",
        r"C:\System Volume Information\file.txt",
        r"C:\pagefile.sys",
        r"C:\hiberfil.sys",
        r"C:\bootmgr",
    ]:
        assert is_protected_path(
            path, windows=True, environ=WINDOWS_ENV
        ), path


def test_component_prefix_does_not_protect_sibling_names():
    assert not is_protected_path(
        r"C:\WindowsBackup\notes.txt", windows=True, environ=WINDOWS_ENV
    )
    assert not is_protected_path(
        r"C:\Windows.old\notes.txt", windows=True, environ=WINDOWS_ENV
    )
    assert not is_protected_path(
        r"C:\Program Files Backup\notes.txt",
        windows=True,
        environ=WINDOWS_ENV,
    )


def test_volume_root_is_protected():
    assert is_protected_path("C:\\", windows=True, environ=WINDOWS_ENV)
    assert is_protected_path("/", windows=False)
    assert path_rejection_reason(
        "C:\\", [r"C:\Users\me"], windows=True, environ=WINDOWS_ENV
    ) == "Path is a protected volume root"


def test_allowed_root_is_required_and_unknown_is_denied():
    assert path_rejection_reason(
        r"C:\Users\me\Downloads\a.txt", [], windows=True
    ) == "No approved scan root"
    assert path_rejection_reason(
        r"C:\Users\me\Downloads\a.txt",
        [r"C:\Users\me\Downloads"],
        windows=True,
        environ=WINDOWS_ENV,
    ) is None
    assert path_rejection_reason(
        r"C:\Users\me\Elsewhere\a.txt",
        [r"C:\Users\me\Downloads"],
        windows=True,
        environ=WINDOWS_ENV,
    ) == "Outside approved scan roots"


def test_preflight_accepts_regular_file_under_approved_root(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("x")

    decision = inspect_path(str(target), [str(tmp_path)])

    assert decision.allowed is True
    assert decision.reason == ""


def test_preflight_rejects_directory_and_missing_path(tmp_path):
    directory = tmp_path / "folder"
    directory.mkdir()
    missing = tmp_path / "missing.txt"

    directory_decision = inspect_path(str(directory), [str(tmp_path)])
    missing_decision = inspect_path(str(missing), [str(tmp_path)])

    assert directory_decision.allowed is False
    assert directory_decision.reason == "Only regular files can be cleaned"
    assert missing_decision.allowed is False
    assert missing_decision.reason == "Path does not exist"


def test_preflight_rejects_symlink(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("x")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not available: {exc}")

    decision = inspect_path(str(link), [str(tmp_path)])

    assert decision.allowed is False
    assert "symbolic link" in decision.reason.lower()


def test_preflight_rejects_reparse_point(monkeypatch, tmp_path):
    target = tmp_path / "reparse.txt"
    target.write_text("x")

    class FakeStat:
        st_mode = stat.S_IFREG | 0o600
        st_file_attributes = 0x400
        st_size = 1

    real_lstat = os.lstat

    def fake_lstat(path):
        if os.fspath(path) == str(target):
            return FakeStat()
        return real_lstat(path)

    from panther.services import cleanup_policy

    monkeypatch.setattr(cleanup_policy.os, "lstat", fake_lstat)

    decision = inspect_path(str(target), [str(tmp_path)])

    assert decision.allowed is False
    assert "reparse" in decision.reason.lower()


def test_inspect_paths_preserves_order_and_reasons(tmp_path):
    first = tmp_path / "a.txt"
    first.write_text("x")
    second = tmp_path / "b.txt"
    second.write_text("y")
    directory = tmp_path / "dir"
    directory.mkdir()

    decisions = inspect_paths(
        [str(first), str(directory), str(second)], [str(tmp_path)]
    )

    assert [item.allowed for item in decisions] == [True, False, True]
    assert decisions[1].reason == "Only regular files can be cleaned"


def _symlink_directory(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not available: {exc}")


def test_parent_symlink_escaping_approved_root_is_rejected(tmp_path):
    approved = tmp_path / "approved"
    outside = tmp_path / "outside"
    approved.mkdir()
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("outside")
    _symlink_directory(approved / "link", outside)

    decision = inspect_path(
        str(approved / "link" / "secret.txt"), [str(approved)]
    )

    assert decision.allowed is False
    assert (
        "symbolic link" in decision.reason.lower()
        or "reparse" in decision.reason.lower()
        or "outside" in decision.reason.lower()
    )


def test_parent_symlink_into_protected_location_is_rejected(
    tmp_path, monkeypatch
):
    from panther.services import cleanup_policy

    approved = tmp_path / "approved"
    protected = tmp_path / "protected"
    approved.mkdir()
    protected.mkdir()
    (protected / "secret.txt").write_text("protected")
    _symlink_directory(approved / "link", protected)
    monkeypatch.setattr(
        cleanup_policy,
        "default_protected_roots",
        lambda windows=None, environ=None: [str(protected)],
    )

    decision = inspect_path(
        str(approved / "link" / "secret.txt"), [str(approved)]
    )

    assert decision.allowed is False
    assert "protected" in decision.reason.lower()


def test_normal_nested_file_remains_eligible(tmp_path):
    approved = tmp_path / "approved"
    nested = approved / "nested" / "deeper"
    nested.mkdir(parents=True)
    target = nested / "file.txt"
    target.write_text("safe")

    decision = inspect_path(str(target), [str(approved)])

    assert decision.allowed is True
    assert decision.reason == ""


def test_parent_reparse_point_simulation_is_rejected(
    tmp_path, monkeypatch
):
    from panther.services import cleanup_policy

    approved = tmp_path / "approved"
    parent = approved / "parent"
    parent.mkdir(parents=True)
    target = parent / "file.txt"
    target.write_text("safe")

    class FakeStat:
        st_mode = stat.S_IFDIR | 0o700
        st_file_attributes = 0x400
        st_size = 0
        st_dev = 0
        st_ino = 0

    real_lstat = os.lstat

    def fake_lstat(path):
        if os.fspath(path) == str(parent):
            return FakeStat()
        return real_lstat(path)

    monkeypatch.setattr(cleanup_policy.os, "lstat", fake_lstat)

    decision = inspect_path(str(target), [str(approved)])

    assert decision.allowed is False
    assert (
        "reparse" in decision.reason.lower()
        or "symbolic link" in decision.reason.lower()
    )

