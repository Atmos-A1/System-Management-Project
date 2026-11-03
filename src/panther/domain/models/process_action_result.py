"""Structured outcomes for process action requests."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from .process_action_request import ProcessActionType
from .process_identity import ProcessIdentity


class ProcessActionStatus(str, Enum):
    REJECTED = "rejected"
    IDENTITY_MISMATCH = "identity_mismatch"
    ALREADY_EXITED = "already_exited"
    REQUEST_SENT = "request_sent"
    EXITED_VERIFIED = "exited_verified"
    STILL_RUNNING = "still_running"
    ACCESS_DENIED = "access_denied"
    VERIFICATION_FAILED = "verification_failed"
    FAILED = "failed"


@dataclass(frozen=True)
class ProcessActionResult:
    """Outcome of an action, distinct from whether a request was sent."""

    request_id: str
    identity: ProcessIdentity
    action: ProcessActionType
    status: ProcessActionStatus
    message: str
    requested_at: datetime
    completed_at: Optional[datetime] = None
    verified: bool = False
    error_code: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id must be a non-empty string")
        if not isinstance(self.identity, ProcessIdentity):
            raise TypeError("identity must be a ProcessIdentity")
        if not isinstance(self.action, ProcessActionType):
            raise TypeError("action must be a ProcessActionType")
        if not isinstance(self.status, ProcessActionStatus):
            raise TypeError("status must be a ProcessActionStatus")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message must be a non-empty string")
        if not isinstance(self.requested_at, datetime):
            raise TypeError("requested_at must be a datetime")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware")
        if self.completed_at is not None:
            if not isinstance(self.completed_at, datetime):
                raise TypeError("completed_at must be a datetime or None")
            if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
                raise ValueError("completed_at must be timezone-aware")
            if self.completed_at < self.requested_at:
                raise ValueError("completed_at cannot precede requested_at")
        if not isinstance(self.verified, bool):
            raise TypeError("verified must be a boolean")
        if self.status == ProcessActionStatus.EXITED_VERIFIED and not self.verified:
            raise ValueError("EXITED_VERIFIED requires verified=True")
        if self.error_code is not None and not isinstance(self.error_code, str):
            raise TypeError("error_code must be a string or None")
