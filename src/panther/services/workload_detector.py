"""Workload detection service (Phase 7)."""

from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import time

try:
    import psutil
except Exception:
    psutil = None

from ..domain.models.workload import (
    ProcessResourceSample,
    SystemResourceSample,
    WorkloadClassification,
)


class WorkloadDetector:
    def __init__(self, config: Optional[Dict] = None):
        default = {
            "cpu_heavy_threshold": 85.0,
            "memory_heavy_threshold": 85.0,
            "cpu_light_threshold": 20.0,
            "memory_light_threshold": 40.0,
            "min_samples": 3,
            "sample_window_seconds": 60,
            "poll_interval_seconds": 5,
        }
        if config:
            default.update(config)
        self.config = default
        self._system_samples: deque = deque(maxlen=20)
        self._process_samples: Dict[int, deque] = {}
        self._last_classification: Optional[WorkloadClassification] = None
        self._last_change_time: Optional[datetime] = None

    def sample_system(self) -> Optional[SystemResourceSample]:
        if psutil is None:
            return None
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            sample = SystemResourceSample(
                cpu_percent=float(cpu) if cpu is not None else 0.0,
                memory_percent=float(mem.percent),
                memory_available=getattr(mem, "available", None),
                memory_total=getattr(mem, "total", None),
            )
            self._system_samples.append(sample)
            return sample
        except Exception:
            return None

    def sample_processes(self) -> List[ProcessResourceSample]:
        samples = []
        if psutil is None:
            return samples
        try:
            for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
                try:
                    info = proc.info
                    pid = info.get("pid")
                    if pid is None:
                        continue
                    name = info.get("name") or ""
                    cpu = info.get("cpu_percent")
                    mem = info.get("memory_info")
                    rss = getattr(mem, "rss", None) if mem else None
                    sample = ProcessResourceSample(
                        pid=int(pid),
                        name=str(name),
                        cpu_percent=float(cpu) if cpu is not None else None,
                        memory_rss=int(rss) if rss is not None else None,
                    )
                    samples.append(sample)
                    if pid not in self._process_samples:
                        self._process_samples[pid] = deque(maxlen=10)
                    self._process_samples[pid].append(sample)
                except Exception:
                    continue
        except Exception:
            pass
        return samples

    def classify_workload(self) -> WorkloadClassification:
        if len(self._system_samples) < self.config["min_samples"]:
            # Try to get more samples
            for _ in range(self.config["min_samples"] - len(self._system_samples)):
                self.sample_system()
                time.sleep(0.1)

        if not self._system_samples:
            return WorkloadClassification(
                classification="unknown",
                confidence=0.0,
                evidence=["No system samples available"],
                pressure="none",
                samples_count=0,
            )

        # Use recent samples, avoid reacting to spikes - use average
        recent = list(self._system_samples)[-self.config["min_samples"]:]
        avg_cpu = sum(s.cpu_percent for s in recent) / len(recent)
        avg_mem = sum(s.memory_percent for s in recent) / len(recent)
        max_cpu = max(s.cpu_percent for s in recent)
        max_mem = max(s.memory_percent for s in recent)

        evidence = []
        evidence.append(f"Avg CPU: {avg_cpu:.1f}%, Max: {max_cpu:.1f}% over {len(recent)} samples")
        evidence.append(f"Avg RAM: {avg_mem:.1f}%, Max: {max_mem:.1f}%")

        cpu_heavy = avg_cpu > self.config["cpu_heavy_threshold"]
        mem_heavy = avg_mem > self.config["memory_heavy_threshold"]
        cpu_light = avg_cpu < self.config["cpu_light_threshold"]
        mem_light = avg_mem < self.config["memory_light_threshold"]

        if cpu_heavy and mem_heavy:
            classification = "combined"
            confidence = min(0.95, 0.7 + (avg_cpu + avg_mem - 170) / 100)
            pressure = "high"
        elif cpu_heavy and not mem_heavy:
            classification = "heavy_cpu"
            confidence = min(0.9, 0.7 + (avg_cpu - 85) / 50)
            pressure = "high" if avg_cpu > 90 else "medium"
        elif mem_heavy and not cpu_heavy:
            classification = "heavy_memory"
            confidence = min(0.9, 0.7 + (avg_mem - 85) / 50)
            pressure = "high" if avg_mem > 90 else "medium"
        elif cpu_light and mem_light:
            classification = "idle"
            confidence = 0.8
            pressure = "none"
        elif cpu_light or (avg_cpu < 40 and avg_mem < 70):
            classification = "light"
            confidence = 0.75
            pressure = "none"
        elif avg_cpu < 70 and avg_mem < 80:
            classification = "normal_interactive"
            confidence = 0.8
            pressure = "low"
        else:
            classification = "unknown"
            confidence = 0.5
            pressure = "medium"

        # Detect change
        now = datetime.now(timezone.utc)
        if self._last_classification and self._last_classification.classification != classification:
            self._last_change_time = now
            evidence.append(f"Workload changed from {self._last_classification.classification}")

        result = WorkloadClassification(
            classification=classification,
            confidence=max(0.0, min(1.0, confidence)),
            evidence=evidence,
            pressure=pressure,
            samples_count=len(self._system_samples),
            metadata={
                "avg_cpu": avg_cpu,
                "avg_mem": avg_mem,
                "max_cpu": max_cpu,
                "max_mem": max_mem,
            },
        )
        self._last_classification = result
        return result

    def get_sustained_consumers(self, min_duration_seconds: int = 30) -> List[Dict]:
        """Identify processes with sustained high resource consumption."""
        consumers = []
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=min_duration_seconds)
        for pid, samples in self._process_samples.items():
            if not samples:
                continue
            recent = [s for s in samples if s.timestamp >= cutoff]
            if len(recent) < 3:
                continue
            avg_cpu = sum(s.cpu_percent or 0 for s in recent) / len(recent)
            avg_mem = sum(s.memory_rss or 0 for s in recent) / len(recent)
            if avg_cpu > 30 or avg_mem > 500 * 1024 * 1024:  # >30% CPU or >500MB
                consumers.append({
                    "pid": pid,
                    "name": recent[-1].name,
                    "avg_cpu": avg_cpu,
                    "avg_memory_mb": avg_mem / (1024 * 1024),
                    "sample_count": len(recent),
                    "sustained": True,
                })
        return sorted(consumers, key=lambda x: x["avg_memory_mb"], reverse=True)
