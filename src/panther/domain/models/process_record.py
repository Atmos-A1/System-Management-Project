"""A point-in-time snapshot of a process."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Optional

from .process_identity import ProcessIdentity


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ProcessRecord:
    """Collected process information; unavailable measurements stay None."""

    identity: ProcessIdentity
    ppid: Optional[int] = None
    username: Optional[str] = None
    status: Optional[str] = None
    cpu_percent: Optional[float] = None
    memory_rss: Optional[int] = None
    memory_vms: Optional[int] = None
    num_threads: Optional[int] = None
    first_seen: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ProcessIdentity):
            raise TypeError("identity must be a ProcessIdentity")
        for field_name in ("ppid", "memory_rss", "memory_vms", "num_threads"):
            value = getattr(self, field_name)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise TypeError("{} must be an integer or None".format(field_name))
                if value < 0:
                    raise ValueError("{} cannot be negative".format(field_name))
        if self.cpu_percent is not None:
            if isinstance(self.cpu_percent, bool) or not isinstance(
                self.cpu_percent, (int, float)
            ):
                raise TypeError("cpu_percent must be a number or None")
            if not math.isfinite(float(self.cpu_percent)) or self.cpu_percent < 0:
                raise ValueError("cpu_percent must be finite and non-negative")
            object.__setattr__(self, "cpu_percent", float(self.cpu_percent))
        if not isinstance(self.first_seen, datetime):
            raise TypeError("first_seen must be a datetime")
        if self.first_seen.tzinfo is None or self.first_seen.utcoffset() is None:
            raise ValueError("first_seen must be timezone-aware")
