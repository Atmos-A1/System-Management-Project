from datetime import datetime, timedelta, timezone

import pytest

from panther.domain.models import (
    ProcessActionRequest, ProcessActionStatus, ProcessActionType, ProcessIdentity,
)
from panther.services.process_graceful_closer import (
    ProcessAuthorizationEvidence, ProcessGracefulCloser,
)
from panther.services.process_authorization import ProcessAuthorizationPolicy
from panther.services.windows_process_adapter import (
    ProcessVerificationResult, ProcessVerificationStatus,
)


def make_identity(created=100.0):
    return ProcessIdentity(2000, created, "editor.exe", r"C:\Apps\editor.exe")


def make_request(action=ProcessActionType.REQUEST_GRACEFUL_CLOSE, confirmed=True):
    return ProcessActionRequest(
        identity=make_identity(), action=action, confirmed=confirmed,
        requested_at=datetime.now(timezone.utc),
    )


class VerifiedAdapter:
    def __init__(self, status=ProcessVerificationStatus.VERIFIED, identity=None):
        self.status = status
        self.identity = identity

    def inspect(self, identity):
        return ProcessVerificationResult(
            status=self.status,
            requested_identity=self.identity or identity,
            observed_create_time=identity.create_time,
            handle_closed=True,
        )


class EvidenceProvider:
    def __init__(self, identity=None, collected_at=None):
        self.identity = identity
        self.collected_at = collected_at or datetime.now(timezone.utc)

    def collect(self, identity):
        return ProcessAuthorizationEvidence(
            identity=self.identity or identity,
            source="test-fixture",
            collected_at=self.collected_at,
            publisher_verified=True,
            signature_valid=True,
            user_owned=True,
            not_service=True,
            not_critical=True,
        )


class FakeBackend:
    def __init__(self, created=100.0, windows=1, wait="exited"):
        self.created = created
        self.windows = windows
        self.wait = wait
        self.opened = []
        self.closed = []
        self.close_requests = []
        self.wait_calls = []

    def open_action_handle(self, pid):
        self.opened.append(pid)
        return object()

    def get_creation_time(self, handle):
        return self.created

    def request_window_close(self, pid):
        self.close_requests.append(pid)
        return self.windows

    def wait_for_exit(self, handle, timeout_ms):
        self.wait_calls.append(timeout_ms)
        if isinstance(self.wait, Exception):
            raise self.wait
        return self.wait

    def close_handle(self, handle):
        self.closed.append(handle)


def classification():
    return {"category": "User application", "can_terminate": True}


def closer(backend, verifier=None, timeout_ms=2500, evidence_provider=None):
    return ProcessGracefulCloser(
        backend=backend,
        verifier=verifier or VerifiedAdapter(),
        authorization_policy=ProcessAuthorizationPolicy(panther_pid=99999),
        evidence_provider=evidence_provider or EvidenceProvider(),
        timeout_ms=timeout_ms,
    )


def test_graceful_close_verifies_exit_and_closes_handle():
    backend = FakeBackend()
    result = closer(backend).close(make_request(), classification())

    assert result.status is ProcessActionStatus.EXITED_VERIFIED
    assert result.verified is True
    assert backend.close_requests == [2000]
    assert backend.wait_calls == [2500]
    assert len(backend.closed) == 1


def test_timeout_reports_still_running_without_escalation():
    backend = FakeBackend(wait="timeout")
    result = closer(backend).close(make_request(), classification())

    assert result.status is ProcessActionStatus.STILL_RUNNING
    assert result.verified is False
    assert "did not force-stop" in result.message
    assert backend.close_requests == [2000]
    assert len(backend.closed) == 1


def test_no_visible_window_does_not_claim_request_was_sent():
    backend = FakeBackend(windows=0)
    result = closer(backend).close(make_request(), classification())

    assert result.status is ProcessActionStatus.FAILED
    assert result.error_code == "NO_CLOSEABLE_WINDOW"
    assert backend.wait_calls == []
    assert len(backend.closed) == 1


def test_pid_reuse_before_close_prevents_window_message():
    backend = FakeBackend(created=200.0)
    result = closer(backend).close(make_request(), classification())

    assert result.status is ProcessActionStatus.IDENTITY_MISMATCH
    assert backend.close_requests == []
    assert backend.wait_calls == []
    assert len(backend.closed) == 1


def test_access_denied_is_reported():
    class DeniedBackend(FakeBackend):
        def open_action_handle(self, pid):
            raise PermissionError("access denied")

    backend = DeniedBackend()
    result = closer(backend).close(make_request(), classification())

    assert result.status is ProcessActionStatus.ACCESS_DENIED
    assert result.error_code == "ACCESS_DENIED"
    assert backend.close_requests == []
    assert backend.closed == []


def test_process_already_gone_is_not_reported_as_success():
    class GoneBackend(FakeBackend):
        def open_action_handle(self, pid):
            raise ProcessLookupError("gone")

    result = closer(GoneBackend()).close(make_request(), classification())
    assert result.status is ProcessActionStatus.ALREADY_EXITED
    assert result.verified is False


def test_force_termination_is_rejected_without_opening_process():
    backend = FakeBackend()
    request = make_request(ProcessActionType.REQUEST_FORCE_TERMINATION)
    result = closer(backend).close(request, classification())

    assert result.status is ProcessActionStatus.REJECTED
    assert result.error_code == "ACTION_NOT_SUPPORTED"
    assert backend.opened == []


def test_authorization_denial_prevents_opening_process_handle():
    backend = FakeBackend()
    result = closer(backend).close(make_request(confirmed=False), classification())

    assert result.status is ProcessActionStatus.REJECTED
    assert result.error_code == "USER_CONFIRMATION_REQUIRED"
    assert backend.opened == []


def test_verification_identity_mismatch_prevents_action():
    other = ProcessIdentity(2000, 300.0, "editor.exe", r"C:\Apps\editor.exe")
    backend = FakeBackend()
    result = closer(
        backend, verifier=VerifiedAdapter(identity=other)
    ).close(make_request(), classification())

    assert result.status is ProcessActionStatus.IDENTITY_MISMATCH
    assert backend.opened == []


def test_wait_failure_is_not_reported_as_exit_and_handle_is_closed():
    backend = FakeBackend(wait=OSError("wait failed"))
    result = closer(backend).close(make_request(), classification())

    assert result.status is ProcessActionStatus.FAILED
    assert result.verified is False
    assert len(backend.closed) == 1


def test_handle_close_failure_overrides_success_with_verification_failure():
    class CloseFailureBackend(FakeBackend):
        def close_handle(self, handle):
            raise OSError("close failed")

    result = closer(CloseFailureBackend()).close(make_request(), classification())
    assert result.status is ProcessActionStatus.VERIFICATION_FAILED
    assert result.error_code == "HANDLE_CLOSE_FAILED"
    assert result.verified is False


def test_missing_evidence_provider_fails_closed():
    backend = FakeBackend()
    service = ProcessGracefulCloser(
        backend=backend, verifier=VerifiedAdapter(),
        authorization_policy=ProcessAuthorizationPolicy(panther_pid=99999),
    )
    result = service.close(make_request(), classification())
    assert result.status is ProcessActionStatus.REJECTED
    assert result.error_code == "EVIDENCE_PROVIDER_UNAVAILABLE"
    assert backend.opened == []


def test_stale_evidence_fails_closed():
    backend = FakeBackend()
    provider = EvidenceProvider(collected_at=datetime.now(timezone.utc) - timedelta(seconds=60))
    result = closer(backend, evidence_provider=provider).close(make_request(), classification())
    assert result.status is ProcessActionStatus.REJECTED
    assert result.error_code == "STALE_EVIDENCE"
    assert backend.opened == []


def test_evidence_for_different_process_instance_fails_closed():
    backend = FakeBackend()
    other = ProcessIdentity(2000, 300.0, "editor.exe", r"C:\Apps\editor.exe")
    provider = EvidenceProvider(identity=other)
    result = closer(backend, evidence_provider=provider).close(make_request(), classification())
    assert result.status is ProcessActionStatus.IDENTITY_MISMATCH
    assert result.error_code == "EVIDENCE_IDENTITY_MISMATCH"
    assert backend.opened == []


def test_invalid_timeout_is_rejected():
    with pytest.raises(ValueError):
        ProcessGracefulCloser(backend=FakeBackend(), timeout_ms=-1)
