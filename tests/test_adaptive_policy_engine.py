from datetime import datetime, timedelta, timezone

from panther.domain.models.process_identity import ProcessIdentity
from panther.domain.models.workload import WorkloadClassification
from panther.services.adaptive_policy_engine import AdaptivePolicyEngine


def workload(label="heavy_memory", confidence=0.9, age=0):
    return WorkloadClassification(
        classification=label, confidence=confidence,
        evidence=["measured memory pressure"], pressure="high", samples_count=5,
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=age),
    )


def test_unknown_or_low_confidence_workload_produces_no_recommendations():
    engine = AdaptivePolicyEngine()
    assert engine.evaluate(workload("unknown"), {}).recommendations == []
    assert engine.evaluate(workload(confidence=0.2), {}).recommendations == []


def test_stale_workload_produces_no_recommendations():
    engine = AdaptivePolicyEngine()
    decision = engine.evaluate(workload(age=120), {})
    assert decision.recommendations == []
    assert decision.context["fresh"] is False


def test_pressure_advice_is_system_level_and_never_close():
    decision = AdaptivePolicyEngine().evaluate(workload(), {})
    assert decision.recommendations
    assert all(rec.target_pid is None for rec in decision.recommendations)
    assert all(rec.action_type == "investigate" for rec in decision.recommendations)
    assert all("will not close" in rec.explanation for rec in decision.recommendations)


def test_process_specific_recommendation_requires_verified_v1_eligibility_and_freshness():
    engine = AdaptivePolicyEngine()
    ident = ProcessIdentity(42, 123.0, "app.exe")
    consumer = {
        "identity": ident, "classification": {"category": "User application"},
        "is_foreground": False, "latest_sample": datetime.now(timezone.utc),
        "measurement_quality": 0.9, "avg_memory_mb": 500, "avg_cpu": 2,
    }
    decision = engine.evaluate(workload(), {}, consumers=[consumer])
    targeted = [rec for rec in decision.recommendations if rec.target_pid is not None]
    assert len(targeted) == 1
    assert targeted[0].target_pid == 42


def test_pid_only_or_foreground_consumers_are_ignored():
    engine = AdaptivePolicyEngine()
    pid_only = {"pid": 42, "name": "app.exe", "avg_memory_mb": 500,
                "classification": {"category": "User application"},
                "is_foreground": False, "latest_sample": datetime.now(timezone.utc),
                "measurement_quality": 1.0}
    foreground = {
        "identity": ProcessIdentity(43, 123.0, "front.exe"),
        "classification": {"category": "User application"}, "is_foreground": True,
        "latest_sample": datetime.now(timezone.utc), "measurement_quality": 1.0,
        "avg_memory_mb": 500,
    }
    decision = engine.evaluate(workload(), {}, consumers=[pid_only, foreground])
    assert all(rec.target_pid is None for rec in decision.recommendations)


def test_termination_is_forced_off_even_if_config_requests_it():
    engine = AdaptivePolicyEngine({"auto_terminate": True, "require_approval": False})
    assert engine.config["auto_terminate"] is False
    assert engine.config["require_approval"] is True
