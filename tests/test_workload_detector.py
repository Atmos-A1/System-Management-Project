"""Tests for workload detection (Phase 7)."""

from panther.services.workload_detector import WorkloadDetector


def test_workload_detector_init():
    detector = WorkloadDetector()
    assert detector is not None
    assert detector.config["min_samples"] >= 1


def test_classify_workload_returns_object():
    detector = WorkloadDetector({"min_samples": 1})
    # Force a sample
    detector.sample_system()
    result = detector.classify_workload()
    assert result is not None
    assert hasattr(result, "classification")
    assert hasattr(result, "confidence")
    assert hasattr(result, "evidence")
    assert hasattr(result, "pressure")
    assert 0 <= result.confidence <= 1


def test_workload_classifications_valid():
    detector = WorkloadDetector({"min_samples": 1})
    detector.sample_system()
    result = detector.classify_workload()
    valid = ["idle", "light", "normal_interactive", "heavy_cpu", "heavy_memory", "combined", "unknown"]
    assert result.classification in valid
