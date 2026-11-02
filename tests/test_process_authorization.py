from datetime import datetime, timezone

import pytest

from panther.domain.models import (
    ProcessActionRequest, ProcessActionType, ProcessIdentity,
)
from panther.services.process_authorization import ProcessAuthorizationPolicy
from panther.services.windows_process_adapter import (
    ProcessVerificationResult, ProcessVerificationStatus,
)


def make_identity(pid=2000, name="editor.exe", created=100.0):
    return ProcessIdentity(pid, created, name, r"C:\Apps\editor.exe")


def make_request(identity=None, action=ProcessActionType.REQUEST_GRACEFUL_CLOSE, confirmed=True):
    return ProcessActionRequest(
        identity=identity or make_identity(), action=action,
        requested_by="user", confirmed=confirmed,
        requested_at=datetime.now(timezone.utc),
    )


def verified(identity):
    return ProcessVerificationResult(
        status=ProcessVerificationStatus.VERIFIED,
        requested_identity=identity, observed_create_time=identity.create_time,
        handle_closed=True,
    )


def classification():
    return {"category": "User application", "can_terminate": True}


def evidence(**overrides):
    result = {
        "publisher_verified": True, "signature_valid": True,
        "user_owned": True, "not_service": True, "not_critical": True,
    }
    result.update(overrides)
    return result


def test_denies_when_identity_verification_is_missing():
    identity = make_identity()
    decision = ProcessAuthorizationPolicy().evaluate(
        make_request(identity), classification(), None, evidence()
    )
    assert not decision.allowed
    assert decision.code == "IDENTITY_NOT_VERIFIED"


def test_denies_identity_mismatch():
    identity = make_identity()
    other = make_identity(created=200.0)
    decision = ProcessAuthorizationPolicy().evaluate(
        make_request(identity), classification(), verified(other), evidence()
    )
    assert not decision.allowed
    assert decision.code in {"IDENTITY_NOT_VERIFIED", "IDENTITY_MISMATCH"}


def test_denies_unverified_windows_result():
    identity = make_identity()
    result = ProcessVerificationResult(
        ProcessVerificationStatus.ACCESS_DENIED, identity, detail="denied"
    )
    decision = ProcessAuthorizationPolicy().evaluate(
        make_request(identity), classification(), result, evidence()
    )
    assert not decision.allowed


def test_denies_unconfirmed_action():
    identity = make_identity()
    decision = ProcessAuthorizationPolicy().evaluate(
        make_request(identity, confirmed=False), classification(), verified(identity), evidence()
    )
    assert not decision.allowed
    assert decision.code == "USER_CONFIRMATION_REQUIRED"


@pytest.mark.parametrize("name", [
    "system", "smss.exe", "csrss.exe", "wininit.exe", "services.exe",
    "lsass.exe", "winlogon.exe", "svchost.exe", "dwm.exe",
])
def test_denies_protected_process_names(name):
    identity = make_identity(name=name)
    decision = ProcessAuthorizationPolicy().evaluate(
        make_request(identity), classification(), verified(identity), evidence()
    )
    assert not decision.allowed
    assert decision.code == "PROTECTED_PROCESS"


def test_denies_panther_self_process():
    identity = make_identity(pid=555)
    decision = ProcessAuthorizationPolicy(panther_pid=555).evaluate(
        make_request(identity), classification(), verified(identity), evidence()
    )
    assert not decision.allowed
    assert decision.code == "PANTHER_SELF_PROTECTION"


def test_denies_unknown_classification():
    identity = make_identity()
    decision = ProcessAuthorizationPolicy().evaluate(
        make_request(identity), {"category": "Unknown / unverified", "can_terminate": False},
        verified(identity), evidence()
    )
    assert not decision.allowed
    assert decision.code == "NOT_USER_APPLICATION"


def test_denies_if_classifier_blocks_process():
    identity = make_identity()
    decision = ProcessAuthorizationPolicy().evaluate(
        make_request(identity), {"category": "User application", "can_terminate": False},
        verified(identity), evidence()
    )
    assert not decision.allowed
    assert decision.code == "CLASSIFIER_BLOCK"


def test_denies_missing_independent_trust_evidence():
    identity = make_identity()
    decision = ProcessAuthorizationPolicy().evaluate(
        make_request(identity), classification(), verified(identity), {}
    )
    assert not decision.allowed
    assert decision.code == "INSUFFICIENT_TRUST_EVIDENCE"


@pytest.mark.parametrize("field", [
    "publisher_verified", "signature_valid", "user_owned", "not_service", "not_critical",
])
def test_each_trust_evidence_field_is_required(field):
    identity = make_identity()
    decision = ProcessAuthorizationPolicy().evaluate(
        make_request(identity), classification(), verified(identity), evidence(**{field: False})
    )
    assert not decision.allowed
    assert decision.code == "INSUFFICIENT_TRUST_EVIDENCE"


def test_authorizes_only_after_all_checks_pass():
    identity = make_identity()
    decision = ProcessAuthorizationPolicy().evaluate(
        make_request(identity), classification(), verified(identity), evidence()
    )
    assert decision.allowed
    assert decision.code == "AUTHORIZED"


def test_force_termination_is_rejected_until_its_separate_phase():
    identity = make_identity()
    request = make_request(identity, ProcessActionType.REQUEST_FORCE_TERMINATION, confirmed=True)
    decision = ProcessAuthorizationPolicy().evaluate(
        request, classification(), verified(identity), evidence()
    )
    assert not decision.allowed
    assert decision.code == "ACTION_NOT_IN_PHASE_SCOPE"


def test_force_termination_is_out_of_scope_for_phase_four():
    identity = make_identity()
    request = make_request(
        identity, action=ProcessActionType.REQUEST_FORCE_TERMINATION, confirmed=True
    )
    decision = ProcessAuthorizationPolicy().evaluate(
        request, classification(), verified(identity), evidence()
    )
    assert not decision.allowed
    assert decision.code == "ACTION_NOT_IN_PHASE_SCOPE"


def test_verification_for_a_different_identity_is_reported_as_mismatch():
    identity = make_identity()
    other = make_identity(created=200.0)
    decision = ProcessAuthorizationPolicy().evaluate(
        make_request(identity), classification(), verified(other), evidence()
    )
    assert not decision.allowed
    assert decision.code == "IDENTITY_MISMATCH"


def test_panther_self_protection_uses_current_process_by_default():
    import os

    identity = make_identity(pid=os.getpid())
    decision = ProcessAuthorizationPolicy().evaluate(
        make_request(identity), classification(), verified(identity), evidence()
    )
    assert not decision.allowed
    assert decision.code == "PANTHER_SELF_PROTECTION"
