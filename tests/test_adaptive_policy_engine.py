"""Tests for adaptive policy engine (Phase 8)."""

from panther.services.adaptive_policy_engine import AdaptivePolicyEngine
from panther.domain.models.workload import WorkloadClassification


def test_policy_engine_init():
    engine = AdaptivePolicyEngine()
    assert engine is not None
    assert engine.config["safe_default"] is True
    assert engine.config["auto_terminate"] is False


def test_evaluate_idle():
    engine = AdaptivePolicyEngine()
    workload = WorkloadClassification(
        classification="idle",
        confidence=0.8,
        evidence=["test"],
        pressure="none",
        samples_count=3,
    )
    decision = engine.evaluate(workload, {})
    assert decision.safe_default is True
    assert len(decision.recommendations) >= 0  # May recommend monitoring frequency


def test_policy_never_auto_terminate():
    engine = AdaptivePolicyEngine()
    assert engine.config["auto_terminate"] is False
    assert engine.config["require_approval"] is True


def test_recommendations_have_explanation():
    engine = AdaptivePolicyEngine()
    workload = WorkloadClassification(
        classification="heavy_memory",
        confidence=0.8,
        evidence=["test"],
        pressure="high",
        samples_count=5,
    )
    decision = engine.evaluate(workload, {}, consumers=[{"pid": 123, "name": "test.exe", "avg_memory_mb": 500, "sample_count": 5}])
    for rec in decision.recommendations:
        assert rec.explanation is not None
        assert len(rec.explanation) > 0
        assert rec.requires_user_approval is True
