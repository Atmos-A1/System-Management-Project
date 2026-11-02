"""Conservative, side-effect-free authorization policy for process actions.

Classification describes what a process may be. Authorization independently
decides whether a specific requested action may proceed. This module never
executes process-control operations.
"""
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ..domain.models import (
    ProcessActionRequest, ProcessActionType, ProcessIdentity,
)
from .windows_process_adapter import (
    ProcessVerificationResult, ProcessVerificationStatus,
)


@dataclass(frozen=True)
class ProcessAuthorizationDecision:
    allowed: bool
    code: str
    reason: str
    identity: ProcessIdentity
    action: ProcessActionType


class ProcessAuthorizationPolicy:
    """Deny by default; require verified identity, confirmation and evidence."""

    PROTECTED_NAMES = frozenset({
        "system", "system idle process", "smss.exe", "csrss.exe",
        "wininit.exe", "services.exe", "lsass.exe", "winlogon.exe",
        "svchost.exe", "dwm.exe", "ntoskrnl.exe", "registry",
    })

    REQUIRED_EVIDENCE = (
        "publisher_verified",
        "signature_valid",
        "user_owned",
        "not_service",
        "not_critical",
    )

    def __init__(self, panther_pid: Optional[int] = None,
                 protected_identities=()):
        self.panther_pid = panther_pid
        self.protected_identities = frozenset(protected_identities)

    def evaluate(
        self,
        request: ProcessActionRequest,
        classification: Optional[Mapping[str, Any]],
        verification: Optional[ProcessVerificationResult],
        authorization_evidence: Optional[Mapping[str, bool]] = None,
    ) -> ProcessAuthorizationDecision:
        identity = request.identity
        action = request.action

        def deny(code, reason):
            return ProcessAuthorizationDecision(False, code, reason, identity, action)

        if identity.pid == self.panther_pid:
            return deny("PANTHER_SELF_PROTECTION", "Panther cannot authorize an action against itself.")
        if identity in self.protected_identities:
            return deny("PROTECTED_IDENTITY", "This process instance is explicitly protected.")
        if identity.name.casefold() in self.PROTECTED_NAMES:
            return deny("PROTECTED_PROCESS", "This process name is on Panther's protected list.")
        if verification is None:
            return deny("IDENTITY_NOT_VERIFIED", "A Windows identity verification result is required.")
        if verification.requested_identity != identity:
            return deny("IDENTITY_MISMATCH", "The verification result belongs to a different process instance.")
        if verification.status is not ProcessVerificationStatus.VERIFIED or not verification.verified:
            return deny("IDENTITY_NOT_VERIFIED", "Windows did not verify this exact process instance.")
        # Phase 4 authorizes graceful-close requests only. Force termination
        # receives a separate authorization design and implementation later.
        if action is not ProcessActionType.REQUEST_GRACEFUL_CLOSE:
            return deny("ACTION_NOT_IN_PHASE_SCOPE", "Only graceful application closure is in scope for this authorization phase.")
        if not request.confirmed:
            return deny("USER_CONFIRMATION_REQUIRED", "The user has not explicitly confirmed this action.")
        if classification is None:
            return deny("CLASSIFICATION_UNAVAILABLE", "Process classification is unavailable.")
        if classification.get("category") != "User application":
            return deny("NOT_USER_APPLICATION", "Only a positively identified user application can be considered.")
        if classification.get("can_terminate") is not True:
            return deny("CLASSIFIER_BLOCK", "The classifier does not consider this process eligible.")
        evidence = authorization_evidence or {}
        missing = [key for key in self.REQUIRED_EVIDENCE if evidence.get(key) is not True]
        if missing:
            return deny(
                "INSUFFICIENT_TRUST_EVIDENCE",
                "Independent authorization evidence is missing: {}.".format(", ".join(missing)),
            )
        if action is ProcessActionType.REQUEST_FORCE_TERMINATION and request.confirmed is not True:
            return deny("FORCE_CONFIRMATION_REQUIRED", "Force termination requires explicit confirmation.")
        return ProcessAuthorizationDecision(
            True, "AUTHORIZED",
            "The requested action passed Panther's authorization checks; execution and outcome verification are separate.",
            identity, action,
        )
