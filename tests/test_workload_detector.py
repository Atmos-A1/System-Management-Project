from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from panther.domain.models.workload import SystemResourceSample, ProcessResourceSample
from panther.services import workload_detector as module
from panther.services.workload_detector import WorkloadDetector


def samples(detector, cpu=10.0, memory=30.0, count=4, step=5):
    now = datetime.now(timezone.utc)
    for i in range(count):
        detector._system_samples.append(SystemResourceSample(
            cpu_percent=cpu, memory_percent=memory, memory_available=1000,
            memory_total=2000, timestamp=now - timedelta(seconds=(count-i-1)*step)))
    return now


def test_classification_does_not_manufacture_samples_or_sleep():
    detector = WorkloadDetector({"min_samples": 3, "min_observation_seconds": 0})
    before = len(detector._system_samples)
    result = detector.classify_workload()
    assert result.classification == "unknown"
    assert len(detector._system_samples) == before


def test_requires_enough_fresh_cpu_and_memory_observations():
    detector = WorkloadDetector({"min_samples": 3, "min_observation_seconds": 0})
    samples(detector, count=2)
    assert detector.classify_workload().classification == "unknown"


def test_classifies_idle_from_sustained_observations():
    detector = WorkloadDetector({"min_samples": 3, "min_observation_seconds": 0})
    samples(detector, cpu=5, memory=25)
    result = detector.classify_workload()
    assert result.classification == "idle"
    assert result.samples_count == 4
    assert 0 < result.confidence <= 0.95


def test_classification_rejects_stale_samples():
    detector = WorkloadDetector({"min_samples": 3, "min_observation_seconds": 0, "sample_window_seconds": 10})
    old = datetime.now(timezone.utc) - timedelta(minutes=5)
    for _ in range(4):
        detector._system_samples.append(SystemResourceSample(10, 30, 1, 2, old))
    assert detector.classify_workload().classification == "unknown"


def test_first_system_cpu_sample_is_unavailable(monkeypatch):
    monkeypatch.setattr(module, "psutil", SimpleNamespace(
        cpu_percent=lambda interval=None: 0.0,
        virtual_memory=lambda: SimpleNamespace(percent=30, available=100, total=200)))
    detector = WorkloadDetector()
    sample = detector.sample_system()
    assert sample.cpu_percent is None
    assert sample.memory_percent == 30


def test_process_sampling_enumerates_once_per_snapshot_and_prunes_stale(monkeypatch):
    class Proc:
        def __init__(self, pid):
            self.info = {"pid": pid, "name": "app.exe", "cpu_percent": 12,
                         "memory_info": SimpleNamespace(rss=1024),
                         "create_time": 123.0, "exe": r"C:\\Program Files\\app.exe"}
    calls = []
    monkeypatch.setattr(module, "psutil", SimpleNamespace(
        process_iter=lambda attrs: (calls.append(attrs) or [Proc(55)]),
        NoSuchProcess=type("NoSuchProcess", (Exception,), {}),
        AccessDenied=type("AccessDenied", (Exception,), {}),
        ZombieProcess=type("ZombieProcess", (Exception,), {}),
    ))
    detector = WorkloadDetector()
    first = detector.sample_processes()
    assert len(calls) == 1
    assert first[0].cpu_percent is None
    assert first[0].create_time == 123.0
    assert len(detector._process_samples) == 1


def test_missing_metrics_do_not_become_zero():
    detector = WorkloadDetector({"min_samples": 3, "min_observation_seconds": 0})
    now = datetime.now(timezone.utc)
    for i in range(3):
        detector._system_samples.append(SystemResourceSample(None, 30, 1, 2, now - timedelta(seconds=10-i*5)))
    result = detector.classify_workload()
    assert result.classification == "unknown"
    assert result.metadata["valid_cpu_samples"] == 0



def test_low_available_memory_is_separate_pressure_evidence():
    detector = WorkloadDetector({"min_samples": 3, "min_observation_seconds": 0})
    now = datetime.now(timezone.utc)
    for i in range(4):
        detector._system_samples.append(SystemResourceSample(
            cpu_percent=15, memory_percent=70, memory_available=100,
            memory_total=2000, timestamp=now - timedelta(seconds=(3-i)*5)))
    result = detector.classify_workload()
    assert result.classification == "heavy_memory"
    assert result.metadata["avg_available_percent"] == 5
