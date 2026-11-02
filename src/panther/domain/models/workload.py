"""Workload detection models."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ProcessResourceSample:
    pid: int
    name: str
    cpu_percent: Optional[float]
    memory_rss: Optional[int]
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class SystemResourceSample:
    cpu_percent: float
    memory_percent: float
    memory_available: Optional[int]
    memory_total: Optional[int]
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class WorkloadClassification:
    classification: str  # idle, light, normal_interactive, heavy_cpu, heavy_memory, combined, unknown
    confidence: float
    evidence: List[str]
    pressure: str  # none, low, medium, high
    samples_count: int
    timestamp: datetime = field(default_factory=_utc_now)
    metadata: Dict[str, object] = field(default_factory=dict)
