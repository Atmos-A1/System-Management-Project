"""Tests for the Process Reliability Foundation domain models."""

from datetime import datetime, timedelta, timezone

import pytest

from panther.domain.models import (
    ProcessActionRequest,
    ProcessActionResult,
    ProcessActionStatus,
    ProcessActionType,
    ProcessIdentity,
    ProcessRecord,
)


def make_identity(pid=1200, create_time=1000.5, name="example.exe", exe=None):
    return ProcessIdentity(pid=pid, create_time=create_time, name=name, exe=exe)


def test_identity_uses_pid_and_creation_time_as_key():
    first = make_identity(name="first.exe", exe="C:/Apps/first.exe")
    same_instance = make_identity(name="renamed.exe", exe="C:/Apps/renamed.exe")
    replacement = make_identity(create_time=1001.0)

    assert first == same_instance
    assert hash(first) == hash(same_instance)
    assert first != replacement


def test_identity_allows_pid_zero_for_system_idle_record():
    identity = make_identity(pid=0)
    assert identity.pid == 0


@pytest.mark.parametrize("pid", [-1, 1.5, True])
def test_identity_rejects_invalid_pid(pid):
    with pytest.raises((TypeError, ValueError)):
        make_identity(pid=pid)


@pytest.mark.parametrize("create_time", [0, -1, float("inf"), float("nan")])
def test_identity_rejects_invalid_creation_time(create_time):
    with pytest.raises(ValueError):
        make_identity(create_time=create_time)


def test_process_record_keeps_unavailable_metrics_as_none():
    record = ProcessRecord(identity=make_identity())

    assert record.cpu_percent is None
    assert record.memory_rss is None
    assert record.memory_vms is None
    assert record.first_seen.tzinfo is not None


def test_process_record_accepts_cpu_above_one_hundred_percent():
    record = ProcessRecord(identity=make_identity(), cpu_percent=165.5)
    assert record.cpu_percent == 165.5


@pytest.mark.parametrize("value", [-0.1, float("inf"), float("nan")])
def test_process_record_rejects_invalid_cpu(value):
    with pytest.raises(ValueError):
        ProcessRecord(identity=make_identity(), cpu_percent=value)


def test_process_record_rejects_naive_timestamp():
    with pytest.raises(ValueError):
        ProcessRecord(
            identity=make_identity(),
            first_seen=datetime(2026, 1, 1),
        )


def test_action_request_has_unique_id_and_safe_confirmation_default():
    first = ProcessActionRequest(
        identity=make_identity(),
        action=ProcessActionType.REQUEST_GRACEFUL_CLOSE,
    )
    second = ProcessActionRequest(
        identity=make_identity(),
        action=ProcessActionType.REQUEST_GRACEFUL_CLOSE,
    )

    assert first.request_id != second.request_id
    assert first.confirmed is False
    assert first.requested_by == "user"
    assert first.requested_at.tzinfo is not None


def test_action_request_rejects_string_action():
    with pytest.raises(TypeError):
        ProcessActionRequest(
            identity=make_identity(),
            action="request_force_termination",
        )


def test_action_result_requires_verified_exit_for_success_status():
    requested_at = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        ProcessActionResult(
            request_id="request-1",
            identity=make_identity(),
            action=ProcessActionType.REQUEST_GRACEFUL_CLOSE,
            status=ProcessActionStatus.EXITED_VERIFIED,
            message="Process exited",
            requested_at=requested_at,
            completed_at=requested_at + timedelta(seconds=1),
            verified=False,
        )


def test_action_result_can_represent_sent_but_unverified_request():
    requested_at = datetime.now(timezone.utc)
    result = ProcessActionResult(
        request_id="request-2",
        identity=make_identity(),
        action=ProcessActionType.REQUEST_GRACEFUL_CLOSE,
        status=ProcessActionStatus.REQUEST_SENT,
        message="Close request sent; exit not yet verified",
        requested_at=requested_at,
    )

    assert result.status is ProcessActionStatus.REQUEST_SENT
    assert result.verified is False
    assert result.completed_at is None
