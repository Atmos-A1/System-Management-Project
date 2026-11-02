"""Resource control authorization policy - separate from process termination."""

from dataclasses import dataclass
from typing import Optional, Mapping, Any
import os

from ..domain.models import ProcessIdentity


PROTECTED_PRIORITY_NAMES = {
    "system", "system idle process", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "winlogon.exe",
    "svchost.exe", "dwm.exe", "ntoskrnl.exe", "registry",
    "csrss", "winlogon"
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
        if identity.pid == self.panther_pid:
            return ResourceControlAuthDecision(False, "PANTHER_SELF_PROTECTION", "Cannot control Panther itself")
        
        if identity.name.lower() in self.protected_names or identity.name.casefold() in self.protected_names:
            return ResourceControlAuthDecision(False, "PROTECTED_PROCESS", "Protected system process")
        
        # Never auto-control foreground
        if is_foreground and automatic_enabled:
            return ResourceControlAuthDecision(False, "FOREGROUND_APP_PROTECTED", "Cannot auto-control foreground applications")
        
        # Unknown processes must remain protected
        if classification is None:
            return ResourceControlAuthDecision(False, "CLASSIFICATION_UNAVAILABLE", "Classification required")
        
        cat = classification.get("category", "")
        if cat not in ("User application",):  # Only user apps in V1
            return ResourceControlAuthDecision(False, "NOT_USER_APPLICATION", "Only user applications eligible in V1")
        
        if classification.get("can_terminate") is False and classification.get("risk_level") in ("High", "Critical"):
            # Be conservative
            pass
        
        if mode == "automatic":
            if not automatic_enabled:
                return ResourceControlAuthDecision(False, "AUTOMATIC_DISABLED", "Automatic control disabled by default")
            if not user_confirmed:  # Even auto needs to be pre-approved or have explicit policy
                return ResourceControlAuthDecision(False, "CONFIRMATION_REQUIRED", "Confirmation required")
        elif mode == "user_approved":
            if not user_confirmed:
                return ResourceControlAuthDecision(False, "USER_CONFIRMATION_REQUIRED", "User must explicitly confirm")
        else:  # recommendation only
            return ResourceControlAuthDecision(False, "RECOMMENDATION_ONLY", "Only recommendations in this mode")
        
        return ResourceControlAuthDecision(True, "AUTHORIZED", "Authorized for priority change")
