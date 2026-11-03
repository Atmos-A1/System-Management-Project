"""Adaptive policy models."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class PolicyRecommendation:
    id: str
    action_type: str  # monitor_frequency, lower_priority, warn, investigate
    target_pid: Optional[int]
    target_name: Optional[str]
    reason: str
    explanation: str
    confidence: float
    measurement_quality: float
    requires_user_approval: bool = True
    reversible: bool = True
    category: str = "recommendation"
    timestamp: datetime = field(default_factory=_utc_now)
    evidence: List[str] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyDecision:
    recommendations: List[PolicyRecommendation]
    policy_name: str
    safe_default: bool = True
    timestamp: datetime = field(default_factory=_utc_now)
    context: Dict[str, object] = field(default_factory=dict)
