"""Evidence-gated adaptive recommendations. This engine never executes actions."""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import uuid

from ..domain.models.policy import PolicyRecommendation, PolicyDecision
from ..domain.models.process_identity import ProcessIdentity
from ..domain.models.workload import WorkloadClassification


class AdaptivePolicyEngine:
    def __init__(self, config: Optional[Dict] = None):
        self.config = {
            "safe_default": True,
            "auto_terminate": False,
            "require_approval": True,
            "max_workload_age_seconds": 20,
            "minimum_confidence": 0.65,
            "minimum_measurement_quality": 0.8,
        }
        if config:
            self.config.update(config)
        # Never allow a caller to enable termination through configuration.
        self.config["auto_terminate"] = False
        self.config["require_approval"] = True
        self.policies = ["default_safe"]

    def evaluate(self, workload: WorkloadClassification, system_info: Dict,
                 consumers: Optional[List[Dict]] = None) -> PolicyDecision:
        recommendations = []
        now = datetime.now(timezone.utc)
        age = (now - workload.timestamp).total_seconds()
        fresh = 0 <= age <= self.config["max_workload_age_seconds"]
        enough_evidence = (
            fresh and workload.classification != "unknown"
            and workload.samples_count >= 3
            and workload.confidence >= self.config["minimum_confidence"]
            and bool(workload.evidence)
        )
        context = {
            "workload": workload.classification,
            "pressure": workload.pressure,
            "confidence": workload.confidence,
            "workload_age_seconds": max(0.0, age),
            "fresh": fresh,
            "evidence_sufficient": enough_evidence,
            "automatic_execution": False,
        }

        if enough_evidence and workload.classification == "idle":
            recommendations.append(PolicyRecommendation(
                id=str(uuid.uuid4()), action_type="monitor_frequency",
                target_pid=None, target_name=None, reason="Sustained low system activity",
                explanation="Recent system measurements indicate low activity. Panther may reduce its own monitoring refresh frequency; no application process will be changed.",
                confidence=workload.confidence, measurement_quality=min(1.0, workload.samples_count / 6),
                requires_user_approval=True, reversible=True, category="monitoring",
                evidence=list(workload.evidence), metadata={"suggested_interval": 10},
            ))
        elif enough_evidence and workload.classification in ("heavy_memory", "heavy_cpu", "combined"):
            # System-level advice is safer than guessing that a high consumer is
            # disposable. Per-process advice requires independent identity,
            # V1 classification, foreground status and fresh measurements.
            title = {
                "heavy_memory": "Sustained memory pressure detected",
                "heavy_cpu": "Sustained CPU pressure detected",
                "combined": "Combined CPU and memory pressure detected",
            }[workload.classification]
            explanation = (
                "Review the applications and work in progress before taking action. "
                "High resource use alone does not show that an application is unnecessary. "
                "Panther will not close, suspend, or reprioritize an application automatically."
            )
            recommendations.append(PolicyRecommendation(
                id=str(uuid.uuid4()), action_type="investigate",
                target_pid=None, target_name=None, reason=title,
                explanation=explanation, confidence=workload.confidence,
                measurement_quality=min(1.0, workload.samples_count / 6),
                requires_user_approval=True, reversible=False, category="system_pressure",
                evidence=list(workload.evidence),
            ))

            for consumer in (consumers or [])[:3]:
                identity = consumer.get("identity")
                classification = consumer.get("classification")
                latest = consumer.get("latest_sample")
                quality = consumer.get("measurement_quality", 0.0)
                if not isinstance(identity, ProcessIdentity):
                    continue
                if not isinstance(classification, dict) or classification.get("category") != "User application":
                    continue
                if consumer.get("is_foreground") is not False:
                    continue
                if not isinstance(latest, datetime) or (now - latest).total_seconds() > 20:
                    continue
                if quality < self.config["minimum_measurement_quality"]:
                    continue
                metrics = []
                if consumer.get("avg_cpu") is not None:
                    metrics.append("average CPU {:.1f}%".format(consumer["avg_cpu"]))
                if consumer.get("avg_memory_mb") is not None:
                    metrics.append("average memory {:.1f} MiB".format(consumer["avg_memory_mb"]))
                recommendations.append(PolicyRecommendation(
                    id=str(uuid.uuid4()), action_type="investigate",
                    target_pid=identity.pid, target_name=identity.name,
                    reason="Measured sustained resource use",
                    explanation="Review {}. This is an investigation prompt, not permission to close or alter the application.".format(" and ".join(metrics)),
                    confidence=min(workload.confidence, quality),
                    measurement_quality=quality, requires_user_approval=True,
                    reversible=False, category="application_observation",
                    evidence=["Process identity includes PID and creation time"] + metrics,
                    metadata={"identity_key": identity.key},
                ))

        return PolicyDecision(
            recommendations=recommendations, policy_name="default_safe",
            safe_default=True, context=context,
        )
