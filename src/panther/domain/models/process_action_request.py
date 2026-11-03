"""User-originated process action requests."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from .process_identity import ProcessIdentity


class ProcessActionType(str, Enum):
    REQUEST_GRACEFUL_CLOSE = "request_graceful_close"
    REQUEST_FORCE_TERMINATION = "request_force_termination"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_request_id() -> str:
    return str(uuid4())


@dataclass(frozen=True)
class ProcessActionRequest:
    """A request to act on one previously identified process instance."""

    identity: ProcessIdentity
    action: ProcessActionType
    requested_by: str = "user"
    confirmed: bool = False
    requested_at: datetime = field(default_factory=_utc_now)
    request_id: str = field(default_factory=_new_request_id)

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ProcessIdentity):
            raise TypeError("identity must be a ProcessIdentity")
        if not isinstance(self.action, ProcessActionType):
            raise TypeError("action must be a ProcessActionType")
        if not isinstance(self.requested_by, str) or not self.requested_by.strip():
            raise ValueError("requested_by must be a non-empty string")
        if not isinstance(self.confirmed, bool):
            raise TypeError("confirmed must be a boolean")
        if not isinstance(self.requested_at, datetime):
            raise TypeError("requested_at must be a datetime")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware")
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id must be a non-empty string")
