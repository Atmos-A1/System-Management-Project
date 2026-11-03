"""Stable identity for one operating-system process instance."""

from dataclasses import dataclass
import math
from typing import Optional


@dataclass(frozen=True, eq=False)
class ProcessIdentity:
    """Identify a process instance without relying on its PID alone.

    PID and creation time form the identity key. Name and executable path are
    supporting metadata and deliberately do not affect equality or hashing.
    """

    pid: int
    create_time: float
    name: str
    exe: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.pid, bool) or not isinstance(self.pid, int):
            raise TypeError("pid must be an integer")
        if self.pid < 0:
            raise ValueError("pid cannot be negative")
        if isinstance(self.create_time, bool) or not isinstance(
            self.create_time, (int, float)
        ):
            raise TypeError("create_time must be a number")
        if not math.isfinite(float(self.create_time)) or self.create_time <= 0:
            raise ValueError("create_time must be a finite positive number")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if self.exe is not None and not isinstance(self.exe, str):
            raise TypeError("exe must be a string or None")
        object.__setattr__(self, "create_time", float(self.create_time))

    @property
    def key(self):
        """Return the stable process-instance key."""
        return self.pid, self.create_time

    def __eq__(self, other) -> bool:
        if not isinstance(other, ProcessIdentity):
            return NotImplemented
        return self.key == other.key

    def __hash__(self) -> int:
        return hash(self.key)
