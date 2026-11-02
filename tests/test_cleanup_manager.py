"""Tests for the safe cleanup manager."""

import json

import pytest

import panther.services.cleanup_manager as cleanup_module
import panther.services.cleanup_policy as policy_module
from panther.services.cleanup_manager import CleanupManager


@pytest.fixture
def manager():
    return CleanupManager(history_recorder=lambda category, detail: None)


def _fake_trash(monkeypatch, moved, fail_on=None):
    monkeypatch.setattr(cleanup_module, "HAS_SEND2TRASH", True)

    def fake_send2trash(path):
        if fail_on is not None and str(path) == str(fail_on):
            raise PermissionError("locked by test")
        moved.append(str(path))

    monkeypatch.setattr(cleanup_module, "send2trash", fake_send2trash)


def test_regular_file_is_moved_to_recycle_bin(tmp_path, manager, monkeypatch):
    target = tmp_path / "file.txt"
    target.write_text("x")
    moved = []
    _fake_trash(monkeypatch, moved)

    result = manager.move_to_recycle_bin(
        [str(target)], allowed_roots=[str(tmp_path)]
    )

    assert result["success"] is True
    assert result["moved"] == 1
    assert result["failed"] == 0
    assert moved == [str(target)]
    assert result["outcomes"] == [
        {"path": str(target), "status": "moved", "reason": ""}
    ]


def test_directory_and_missing_paths_are_rejected_before_trash(
    tmp_path, manager, monkeypatch
):
    directory = tmp_path / "folder"
    directory.mkdir()
    missing = tmp_path / "missing.txt"
    moved = []
    _fake_trash(monkeypatch, moved)

    result = manager.move_to_recycle_bin(
        [str(directory), str(missing)], allowed_roots=[str(tmp_path)]
    )

    assert result["success"] is False
    assert result["moved"] == 0
    assert result["failed"] == 2
    assert moved == []
    assert all(item["status"] == "rejected" for item in result["outcomes"])


def test_default_denies_when_no_allowed_root(manager, tmp_path, monkeypatch):
    target = tmp_path / "file.txt"
    target.write_text("x")
    moved = []
    _fake_trash(monkeypatch, moved)

    result = manager.move_to_recycle_bin([str(target)])

    assert result["success"] is False
    assert result["moved"] == 0
    assert moved == []
    assert "approved scan root" in result["outcomes"][0]["reason"]


def test_protected_path_is_rejected(tmp_path, manager, monkeypatch):
    target = tmp_path / "file.txt"
    target.write_text("x")
    moved = []
    _fake_trash(monkeypatch, moved)
    monkeypatch.setattr(
        policy_module,
        "default_protected_roots",
        lambda windows=None, environ=None: [str(tmp_path)],
    )

    result = manager.move_to_recycle_bin(
        [str(target)], allowed_roots=[str(tmp_path)]
    )

    assert result["success"] is False
    assert moved == []
    assert "protected" in result["outcomes"][0]["reason"].lower()


def test_symlink_is_rejected(tmp_path, manager, monkeypatch):
    target = tmp_path / "target.txt"
    target.write_text("x")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not available: {exc}")
    moved = []
    _fake_trash(monkeypatch, moved)

    result = manager.move_to_recycle_bin(
        [str(link)], allowed_roots=[str(tmp_path)]
    )

    assert result["success"] is False
    assert moved == []
    assert "symbolic link" in result["outcomes"][0]["reason"].lower()


def test_send2trash_unavailable_never_falls_back_to_delete(
    tmp_path, manager, monkeypatch
):
    target = tmp_path / "file.txt"
    target.write_text("x")
    monkeypatch.setattr(cleanup_module, "HAS_SEND2TRASH", False)
    monkeypatch.setattr(cleanup_module, "send2trash", None)

    result = manager.move_to_recycle_bin(
        [str(target)], allowed_roots=[str(tmp_path)]
    )

    assert result["success"] is False
    assert result["moved"] == 0
    assert target.exists()
    assert "send2trash" in result["error"].lower()


def test_per_file_failure_is_reported(tmp_path, manager, monkeypatch):
    first = tmp_path / "a.txt"
    first.write_text("x")
    second = tmp_path / "b.txt"
    second.write_text("y")
    moved = []
    _fake_trash(monkeypatch, moved, fail_on=second)

    result = manager.move_to_recycle_bin(
        [str(first), str(second)], allowed_roots=[str(tmp_path)]
    )

    assert result["success"] is True
    assert result["moved"] == 1
    assert result["failed"] == 1
    assert [item["status"] for item in result["outcomes"]] == [
        "moved",
        "failed",
    ]
    assert "locked" in result["outcomes"][1]["reason"]


def test_revalidates_immediately_before_trash(tmp_path, manager, monkeypatch):
    first = tmp_path / "a.txt"
    first.write_text("x")
    second = tmp_path / "b.txt"
    second.write_text("y")
    moved = []
    _fake_trash(monkeypatch, moved)
    original = cleanup_module.send2trash

    def replace_second(path):
        if str(path) == str(first):
            second.unlink()
            try:
                second.symlink_to(first)
            except (OSError, NotImplementedError) as exc:
                pytest.skip(f"symlinks not available: {exc}")
        original(path)

    monkeypatch.setattr(cleanup_module, "send2trash", replace_second)

    result = manager.move_to_recycle_bin(
        [str(first), str(second)], allowed_roots=[str(tmp_path)]
    )

    assert result["moved"] == 1
    assert result["outcomes"][1]["status"] == "rejected"
    assert "symbolic link" in result["outcomes"][1]["reason"].lower()


def test_history_records_each_outcome(tmp_path, monkeypatch):
    target = tmp_path / "file.txt"
    target.write_text("x")
    moved = []
    _fake_trash(monkeypatch, moved)
    events = []
    manager = CleanupManager(
        history_recorder=lambda category, detail: events.append(
            (category, json.loads(detail))
        )
    )

    result = manager.move_to_recycle_bin(
        [str(target)], allowed_roots=[str(tmp_path)]
    )

    assert result["moved"] == 1
    assert events
    category, detail = events[0]
    assert category == "storage_cleanup"
    assert detail["outcomes"][0]["status"] == "moved"


def test_history_failure_does_not_change_cleanup_result(
    tmp_path, monkeypatch
):
    target = tmp_path / "file.txt"
    target.write_text("x")
    moved = []
    _fake_trash(monkeypatch, moved)

    def failing_recorder(category, detail):
        raise RuntimeError("history unavailable")

    manager = CleanupManager(history_recorder=failing_recorder)
    result = manager.move_to_recycle_bin(
        [str(target)], allowed_roots=[str(tmp_path)]
    )

    assert result["success"] is True
    assert result["moved"] == 1
    assert moved == [str(target)]


def test_permanent_delete_is_hard_disabled(manager, tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("x")

    with pytest.raises(PermissionError):
        manager.permanent_delete([str(target)])

    assert target.exists()


def test_preflight_is_advisory_and_reports_rejections(tmp_path, manager):
    target = tmp_path / "file.txt"
    target.write_text("x")
    directory = tmp_path / "dir"
    directory.mkdir()

    result = manager.preflight_cleanup(
        [str(target), str(directory)], [str(tmp_path)]
    )

    assert [item["allowed"] for item in result["decisions"]] == [
        True,
        False,
    ]
    assert result["allowed"] == [str(target)]
    assert len(result["rejected"]) == 1


def test_parent_symlink_rejection_prevents_send2trash(
    tmp_path, manager, monkeypatch
):
    approved = tmp_path / "approved"
    outside = tmp_path / "outside"
    approved.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("outside")
    link = approved / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not available: {exc}")
    target = link / "secret.txt"
    moved = []
    _fake_trash(monkeypatch, moved)

    result = manager.move_to_recycle_bin(
        [str(target)], allowed_roots=[str(approved)]
    )

    assert result["moved"] == 0
    assert moved == []
    assert result["outcomes"][0]["status"] == "rejected"
    assert (
        "symbolic link" in result["outcomes"][0]["reason"].lower()
        or "reparse" in result["outcomes"][0]["reason"].lower()
        or "outside" in result["outcomes"][0]["reason"].lower()
    )

