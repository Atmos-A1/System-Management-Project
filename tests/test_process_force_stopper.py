from datetime import datetime, timezone

from panther.domain.models import (
    ProcessActionRequest, ProcessActionStatus, ProcessActionType, ProcessIdentity,
)
from panther.services.process_force_stopper import ProcessForceStopper
from panther.services.process_graceful_closer import ProcessAuthorizationEvidence
from panther.services.windows_process_adapter import (
    ProcessVerificationResult, ProcessVerificationStatus,
)


IDENTITY = ProcessIdentity(321, 100.0, "editor.exe", r"C:\Apps\editor.exe")


class VerifiedProcess:
    def inspect(self, identity):
        return ProcessVerificationResult(
            ProcessVerificationStatus.VERIFIED, identity,
            observed_create_time=identity.create_time, handle_closed=True,
        )


class EvidenceProvider:
    def collect(self, identity):
        return ProcessAuthorizationEvidence(
            identity=identity, source="test fixture", collected_at=datetime.now(timezone.utc),
            publisher_verified=True, signature_valid=True, user_owned=True,
            not_service=True, not_critical=True,
        )


class FakeBackend:
    def __init__(self, create_time=100.0, outcome="exited"):
        self.create_time = create_time
        self.outcome = outcome
        self.terminated = False
        self.closed = False

    def open_action_handle(self, pid):
        assert pid == IDENTITY.pid
        return object()

    def get_creation_time(self, handle):
        return self.create_time

    def terminate(self, handle):
        self.terminated = True

    def wait_for_exit(self, handle, timeout_ms):
        return self.outcome

    def close_handle(self, handle):
        self.closed = True


def request(confirmed=True):
    return ProcessActionRequest(
        identity=IDENTITY, action=ProcessActionType.REQUEST_FORCE_TERMINATION,
        confirmed=confirmed,
    )


def classification(can_terminate=True):
    return {"category": "User application", "can_terminate": can_terminate}


def test_force_stop_fails_closed_without_trusted_provider():
    backend = FakeBackend()
    service = ProcessForceStopper(backend=backend, verifier=VerifiedProcess())
    result = service.force_stop(request(), classification())
    assert result.status is ProcessActionStatus.REJECTED
    assert result.error_code == "EVIDENCE_PROVIDER_UNAVAILABLE"
    assert not backend.terminated


def test_force_stop_requires_explicit_confirmation():
    backend = FakeBackend()
    service = ProcessForceStopper(
        backend=backend, verifier=VerifiedProcess(), evidence_provider=EvidenceProvider()
    )
    result = service.force_stop(request(False), classification())
    assert result.status is ProcessActionStatus.REJECTED
    assert result.error_code == "CONFIRMATION_REQUIRED"
    assert not backend.terminated


def test_force_stop_rejects_pid_reuse_before_termination():
    backend = FakeBackend(create_time=200.0)
    service = ProcessForceStopper(
        backend=backend, verifier=VerifiedProcess(), evidence_provider=EvidenceProvider()
    )
    result = service.force_stop(request(), classification())
    assert result.status is ProcessActionStatus.IDENTITY_MISMATCH
    assert not backend.terminated
    assert backend.closed


def test_force_stop_reports_verified_exit_and_closes_handle():
    backend = FakeBackend(outcome="exited")
    service = ProcessForceStopper(
        backend=backend, verifier=VerifiedProcess(), evidence_provider=EvidenceProvider()
    )
    result = service.force_stop(request(), classification())
    assert result.status is ProcessActionStatus.EXITED_VERIFIED
    assert result.verified
    assert backend.terminated
    assert backend.closed


def test_force_stop_never_reports_success_without_exit_verification():
    backend = FakeBackend(outcome="timeout")
    service = ProcessForceStopper(
        backend=backend, verifier=VerifiedProcess(), evidence_provider=EvidenceProvider()
    )
    result = service.force_stop(request(), classification())
    assert result.status is ProcessActionStatus.VERIFICATION_FAILED
    assert not result.verified
    assert backend.closed


def test_force_stop_rejects_classification_that_is_not_authorized():
    backend = FakeBackend()
    service = ProcessForceStopper(
        backend=backend, verifier=VerifiedProcess(), evidence_provider=EvidenceProvider()
    )
    result = service.force_stop(request(), classification(False))
    assert result.status is ProcessActionStatus.REJECTED
    assert result.error_code == "CLASSIFIER_BLOCK"
    assert not backend.terminated
