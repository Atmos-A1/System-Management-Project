"""Resource control models."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ControlAction:
    id: str
    action_type: str  # set_priority, restore_priority, adjust_monitoring
    target_pid: Optional[int]
    target_name: Optional[str]
    previous_state: Dict[str, object]
    new_state: Dict[str, object]
    reason: str
    mode: str  # recommendation, user_approved, automatic
    reversible: bool = True
    rollback_data: Dict[str, object] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utc_now)
    result: str = "pending"  # pending, success, failed, rolled_back
    error: Optional[str] = None
    verified: bool = False
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ControlHistory:
    actions: List[ControlAction] = field(default_factory=list)
    automatic_enabled: bool = False
    mode: str = "recommendation"  # recommendation, simulation, adaptive
