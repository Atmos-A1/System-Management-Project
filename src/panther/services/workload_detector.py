"""Workload detection service (Phase 7) - corrected."""

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
            "min_samples_for_sustained": 3,
        }
        if config:
            default.update(config)
        self.config = default
        self._system_samples: deque = deque(maxlen=30)
        self._process_samples: Dict[tuple, deque] = {}  # (pid, create_time)
        self._process_identities = {}  # (pid, create_time) -> info
        self._last_classification: Optional[WorkloadClassification] = None
        self._last_change_time: Optional[datetime] = None

    def sample_system(self) -> Optional[SystemResourceSample]:
        """Non-blocking style - call from background worker only."""
        if psutil is None:
            return None
        try:
            cpu = psutil.cpu_percent(interval=None)  # non-blocking
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
            for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "create_time"]):
                try:
                    info = proc.info
                    pid = info.get("pid")
                    if pid is None:
                        continue
                    create_time = info.get("create_time")
                    if create_time is None:
                        continue
                    key = (int(pid), float(create_time))
                    name = info.get("name") or ""
                    cpu = info.get("cpu_percent")
                    mem = info.get("memory_info")
                    rss = getattr(mem, "rss", None) if mem else None
                    sample = ProcessResourceSample(
                        pid=int(pid),
                        name=str(name),
                        cpu_percent=float(cpu) if cpu is not None and cpu >= 0 else None,
                        memory_rss=int(rss) if rss is not None and rss >= 0 else None,
                    )
                    samples.append(sample)
                    if key not in self._process_samples:
                        self._process_samples[key] = deque(maxlen=15)
                    self._process_samples[key].append(sample)
                    self._process_identities[key] = {"name": name, "pid": pid}
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception:
                    continue
            # Remove stale
            active = set((int(p.info.get("pid")), float(p.info.get("create_time"))) 
                         for p in psutil.process_iter(["pid", "create_time"]) 
                         if p.info.get("pid") is not None and p.info.get("create_time") is not None)
            for key in list(self._process_samples):
                if key not in active:
                    del self._process_samples[key]
                    self._process_identities.pop(key, None)
        except Exception:
            pass
        return samples

    def classify_workload(self) -> WorkloadClassification:
        if len(self._system_samples) < self.config["min_samples"]:
            for _ in range(max(0, self.config["min_samples"] - len(self._system_samples))):
                self.sample_system()
                time.sleep(0.05)

        if not self._system_samples:
            return WorkloadClassification(
                classification="unknown",
                confidence=0.0,
                evidence=["No system samples available"],
                pressure="none",
                samples_count=0,
            )

        recent = list(self._system_samples)[-self.config["min_samples"]:]
        # Filter out None/invalid
        cpu_vals = [s.cpu_percent for s in recent if s.cpu_percent is not None and s.cpu_percent >= 0]
        mem_vals = [s.memory_percent for s in recent if s.memory_percent is not None]
        if not cpu_vals or not mem_vals:
            return WorkloadClassification(
                classification="unknown",
                confidence=0.0,
                evidence=["Insufficient valid measurements"],
                pressure="none",
                samples_count=len(recent),
            )
        avg_cpu = sum(cpu_vals) / len(cpu_vals)
        avg_mem = sum(mem_vals) / len(mem_vals)
        max_cpu = max(cpu_vals)
        max_mem = max(mem_vals)
        data_quality = min(1.0, len(cpu_vals) / len(recent))

        evidence = []
        evidence.append(f"Avg CPU: {avg_cpu:.1f}%, Max: {max_cpu:.1f}% over {len(cpu_vals)} valid samples")
        evidence.append(f"Avg RAM: {avg_mem:.1f}%, Max: {max_mem:.1f}%")
        evidence.append(f"Data quality: {data_quality:.0%}")

        cpu_heavy = avg_cpu > self.config["cpu_heavy_threshold"]
        mem_heavy = avg_mem > self.config["memory_heavy_threshold"]
        cpu_light = avg_cpu < self.config["cpu_light_threshold"]
        mem_light = avg_mem < self.config["memory_light_threshold"]

        if cpu_heavy and mem_heavy:
            classification = "combined"
            confidence = min(0.95, 0.7 * data_quality + (avg_cpu + avg_mem - 170) / 200)
            pressure = "high"
        elif cpu_heavy and not mem_heavy:
            classification = "heavy_cpu"
            confidence = min(0.9, 0.7 * data_quality + (avg_cpu - 85) / 100)
            pressure = "high" if avg_cpu > 90 else "medium"
        elif mem_heavy and not cpu_heavy:
            classification = "heavy_memory"
            confidence = min(0.9, 0.7 * data_quality + (avg_mem - 85) / 100)
            pressure = "high" if avg_mem > 90 else "medium"
        elif cpu_light and mem_light:
            classification = "idle"
            confidence = 0.8 * data_quality
            pressure = "none"
        elif cpu_light or (avg_cpu < 40 and avg_mem < 70):
            classification = "light"
            confidence = 0.75 * data_quality
            pressure = "none"
        elif avg_cpu < 70 and avg_mem < 80:
            classification = "normal_interactive"
            confidence = 0.8 * data_quality
            pressure = "low"
        else:
            classification = "unknown"
            confidence = 0.5 * data_quality
            pressure = "medium"

        now = datetime.now(timezone.utc)
        if self._last_classification and self._last_classification.classification != classification:
            self._last_change_time = now
            evidence.append(f"Workload changed from {self._last_classification.classification}")

        result = WorkloadClassification(
            classification=classification,
            confidence=max(0.0, min(1.0, confidence)),
            evidence=evidence,
            pressure=pressure,
            samples_count=len(cpu_vals),
            metadata={
                "avg_cpu": avg_cpu,
                "avg_mem": avg_mem,
                "max_cpu": max_cpu,
                "max_mem": max_mem,
                "data_quality": data_quality,
            },
        )
        self._last_classification = result
        return result

    def get_sustained_consumers(self, min_duration_seconds: int = 30) -> List[Dict]:
        consumers = []
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=min_duration_seconds)
        for key, samples in self._process_samples.items():
            if not samples:
                continue
            recent = [s for s in samples if s.timestamp >= cutoff]
            if len(recent) < self.config["min_samples_for_sustained"]:
                continue
            cpu_vals = [s.cpu_percent for s in recent if s.cpu_percent is not None]
            mem_vals = [s.memory_rss for s in recent if s.memory_rss is not None]
            if not cpu_vals or not mem_vals:
                continue
            avg_cpu = sum(cpu_vals) / len(cpu_vals)
            avg_mem = sum(mem_vals) / len(mem_vals)
            if avg_cpu > 25 or avg_mem > 300 * 1024 * 1024:
                pid, ctime = key
                consumers.append({
                    "pid": pid,
                    "create_time": ctime,
                    "name": recent[-1].name,
                    "avg_cpu": avg_cpu,
                    "avg_memory_mb": avg_mem / (1024 * 1024),
                    "sample_count": len(recent),
                    "sustained": True,
                    "key": key,
                })
        return sorted(consumers, key=lambda x: (x["avg_memory_mb"], x["avg_cpu"]), reverse=True)
