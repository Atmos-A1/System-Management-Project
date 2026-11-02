"""Fail-closed authorization for reversible process priority changes."""
from dataclasses import dataclass
from typing import Optional, Mapping, Any
import os

from ..domain.models import ProcessIdentity

PROTECTED_PRIORITY_NAMES = {
    "system", "system idle process", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "winlogon.exe",
    "svchost.exe", "dwm.exe", "ntoskrnl.exe", "registry",
    "explorer.exe", "fontdrvhost.exe", "runtimebroker.exe",
}


@dataclass(frozen=True)
class ResourceControlAuthDecision:
    allowed: bool
    code: str
    reason: str


class ResourceControlAuthorizationPolicy:
    def __init__(self, panther_pid: Optional[int] = None):
        self.panther_pid = os.getpid() if panther_pid is None else panther_pid
        self.protected_names = PROTECTED_PRIORITY_NAMES

    def authorize_priority_change(self, identity: ProcessIdentity,
                                  classification: Optional[Mapping[str, Any]] = None,
                                  is_foreground: bool = False,
                                  user_confirmed: bool = False,
                                  automatic_enabled: bool = False,
                                  mode: str = "user_approved") -> ResourceControlAuthDecision:
        if not isinstance(identity, ProcessIdentity):
            return ResourceControlAuthDecision(False, "INVALID_IDENTITY", "A verified process identity is required")
        if identity.pid == self.panther_pid:
            return ResourceControlAuthDecision(False, "PANTHER_SELF_PROTECTION", "Cannot control Panther itself")
        if identity.name.casefold() in self.protected_names:
            return ResourceControlAuthDecision(False, "PROTECTED_PROCESS", "Protected system process")
        if is_foreground and mode == "automatic":
            return ResourceControlAuthDecision(False, "FOREGROUND_APP_PROTECTED", "Automatic control never targets the foreground application")
        if not isinstance(classification, Mapping):
            return ResourceControlAuthDecision(False, "CLASSIFICATION_UNAVAILABLE", "Classification required")
        if classification.get("category") != "User application":
            return ResourceControlAuthDecision(False, "NOT_USER_APPLICATION", "Only V1 user-application candidates are eligible")
        # Classification is only an eligibility gate, never a substitute for
        # the same-handle OS identity check performed by the adapter.
        if mode == "automatic":
            if not automatic_enabled:
                return ResourceControlAuthDecision(False, "AUTOMATIC_DISABLED", "Automatic control is disabled")
            if not user_confirmed:
                return ResourceControlAuthDecision(False, "CONFIRMATION_REQUIRED", "Explicit opt-in is required")
        elif mode == "user_approved":
            if not user_confirmed:
                return ResourceControlAuthDecision(False, "USER_CONFIRMATION_REQUIRED", "User must explicitly confirm")
        else:
            return ResourceControlAuthDecision(False, "RECOMMENDATION_ONLY", "Recommendation mode cannot execute actions")
        return ResourceControlAuthDecision(True, "AUTHORIZED", "Authorized for reversible priority change")
