"""Adaptive policy engine (Phase 8)."""

from datetime import datetime, timezone
from typing import Dict, List, Optional
import uuid

from ..domain.models.policy import PolicyRecommendation, PolicyDecision
from ..domain.models.workload import WorkloadClassification


class AdaptivePolicyEngine:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {
            "safe_default": True,
            "auto_terminate": False,  # NEVER auto-terminate
            "require_approval": True,
        }
        self.policies = ["default_safe"]

    def evaluate(self, workload: WorkloadClassification, 
                 system_info: Dict,
                 consumers: Optional[List[Dict]] = None) -> PolicyDecision:
        recommendations = []
        consumers = consumers or []

        if workload.classification == "idle":
            recommendations.append(PolicyRecommendation(
                id=str(uuid.uuid4()),
                action_type="monitor_frequency",
                target_pid=None,
                target_name=None,
                reason="System is idle",
                explanation="During idle periods, reduce monitoring frequency to save resources. No applications need to be terminated.",
                confidence=workload.confidence,
                measurement_quality=min(1.0, workload.samples_count / 10.0),
                requires_user_approval=True,
                reversible=True,
                category="optimization",
                evidence=workload.evidence,
                metadata={"suggested_interval": 10},
            ))
        elif workload.classification == "heavy_memory":
            for consumer in consumers[:3]:  # Top contributors
                if consumer.get("avg_memory_mb", 0) > 200:
                    recommendations.append(PolicyRecommendation(
                        id=str(uuid.uuid4()),
                        action_type="investigate",
                        target_pid=consumer["pid"],
                        target_name=consumer["name"],
                        reason="High memory pressure from sustained consumer",
                        explanation=f"{consumer['name']} has sustained high memory usage ({consumer['avg_memory_mb']:.1f}MB). Consider investigating - do NOT terminate without understanding if it's needed.",
                        confidence=0.75,
                        measurement_quality=0.8,
                        requires_user_approval=True,
                        reversible=True,
                        category="memory_pressure",
                        evidence=[f"Avg memory: {consumer['avg_memory_mb']:.1f}MB over {consumer['sample_count']} samples"],
                        metadata={"avg_memory_mb": consumer["avg_memory_mb"]},
                    ))
        elif workload.classification == "heavy_cpu":
            for consumer in consumers[:3]:
                if consumer.get("avg_cpu", 0) > 40:
                    recommendations.append(PolicyRecommendation(
                        id=str(uuid.uuid4()),
                        action_type="investigate",
                        target_pid=consumer["pid"],
                        target_name=consumer["name"],
                        reason="Sustained CPU pressure",
                        explanation=f"{consumer['name']} shows sustained CPU usage. Prioritize system responsiveness; avoid interfering with foreground apps.",
                        confidence=0.75,
                        measurement_quality=0.8,
                        requires_user_approval=True,
                        reversible=True,
                        category="cpu_pressure",
                        evidence=[f"Avg CPU: {consumer['avg_cpu']:.1f}%"],
                        metadata={"avg_cpu": consumer["avg_cpu"]},
                    ))
        elif workload.classification == "combined":
            recommendations.append(PolicyRecommendation(
                id=str(uuid.uuid4()),
                action_type="investigate",
                target_pid=None,
                target_name=None,
                reason="Combined CPU and memory pressure",
                explanation="System under combined pressure. Focus on non-essential background apps. Never auto-terminate critical processes.",
                confidence=workload.confidence,
                measurement_quality=0.85,
                requires_user_approval=True,
                reversible=True,
                category="pressure",
                evidence=workload.evidence,
            ))

        return PolicyDecision(
            recommendations=recommendations,
            policy_name="default_safe",
            safe_default=True,
            context={
                "workload": workload.classification,
                "pressure": workload.pressure,
                "confidence": workload.confidence,
            },
        )
