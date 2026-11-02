"""Non-blocking, timestamped workload measurement and classification."""
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

from ..domain.models.process_identity import ProcessIdentity
from ..domain.models.workload import ProcessResourceSample, SystemResourceSample, WorkloadClassification


class WorkloadDetector:
    def __init__(self, config: Optional[Dict] = None):
        defaults = {
            "cpu_heavy_threshold": 85.0, "memory_heavy_threshold": 85.0,
            "cpu_light_threshold": 20.0, "memory_light_threshold": 40.0,
            "min_samples": 3, "sample_window_seconds": 60,
            "min_observation_seconds": 10, "min_samples_for_sustained": 3,
        }
        if config:
            defaults.update(config)
        self.config = defaults
        self._system_samples = deque(maxlen=60)
        self._process_samples: Dict[tuple, deque] = {}
        self._process_identities = {}
        self._system_cpu_primed = False
        self._process_cpu_primed = set()
        self._last_classification = None

    def sample_system(self) -> Optional[SystemResourceSample]:
        """Take one non-blocking sample; the first CPU reading is unavailable."""
        if psutil is None:
            return None
        try:
            raw_cpu = psutil.cpu_percent(interval=None)
            cpu = float(raw_cpu) if self._system_cpu_primed and raw_cpu is not None else None
            self._system_cpu_primed = True
            memory = psutil.virtual_memory()
            sample = SystemResourceSample(
                cpu_percent=cpu,
                memory_percent=float(memory.percent) if memory.percent is not None else None,
                memory_available=getattr(memory, "available", None),
                memory_total=getattr(memory, "total", None),
            )
            self._system_samples.append(sample)
            return sample
        except Exception:
            return None

    def sample_processes(self, cancel_check=None) -> List[ProcessResourceSample]:
        """Enumerate once, update samples, and prune stale identities from that snapshot."""
        if psutil is None:
            return []
        samples, active = [], set()
        try:
            iterator = psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "create_time", "exe", "username"])
            cancelled = False
            for proc in iterator:
                if cancel_check is not None and cancel_check():
                    cancelled = True
                    break
                try:
                    info = proc.info
                    pid, created = info.get("pid"), info.get("create_time")
                    if pid is None or created is None:
                        continue
                    key = (int(pid), float(created))
                    active.add(key)
                    first_seen = key not in self._process_cpu_primed
                    self._process_cpu_primed.add(key)
                    raw_cpu = info.get("cpu_percent")
                    cpu = None if first_seen or raw_cpu is None or raw_cpu < 0 else float(raw_cpu)
                    mem = info.get("memory_info")
                    rss = getattr(mem, "rss", None) if mem is not None else None
                    rss = int(rss) if rss is not None and rss >= 0 else None
                    sample = ProcessResourceSample(
                        pid=int(pid), name=str(info.get("name") or "Unknown"),
                        cpu_percent=cpu, memory_rss=rss, create_time=float(created),
                        exe=info.get("exe"), username=info.get("username"),
                    )
                    samples.append(sample)
                    self._process_samples.setdefault(key, deque(maxlen=30)).append(sample)
                    self._process_identities[key] = {"name": sample.name, "exe": sample.exe, "username": sample.username}
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception:
                    continue
        except Exception:
            return samples

        if cancelled:
            return samples
        stale = set(self._process_samples) - active
        for key in stale:
            self._process_samples.pop(key, None)
            self._process_identities.pop(key, None)
            self._process_cpu_primed.discard(key)
        return samples

    def classify_workload(self, now: Optional[datetime] = None) -> WorkloadClassification:
        """Classify existing observations only; never sleeps or samples on the caller thread."""
        now = now or datetime.now(timezone.utc)
        window = timedelta(seconds=max(1, self.config["sample_window_seconds"]))
        recent = [s for s in self._system_samples if timedelta(0) <= now - s.timestamp <= window]
        min_samples = max(1, int(self.config["min_samples"]))
        cpu_vals = [s.cpu_percent for s in recent if s.cpu_percent is not None]
        mem_vals = [s.memory_percent for s in recent if s.memory_percent is not None]
        span = (recent[-1].timestamp - recent[0].timestamp).total_seconds() if len(recent) > 1 else 0.0
        min_span = max(0.0, float(self.config.get("min_observation_seconds", 10)))
        if len(recent) < min_samples or len(cpu_vals) < min_samples or len(mem_vals) < min_samples or span < min_span:
            reasons = ["Insufficient fresh observations; classification is unavailable"]
            if len(cpu_vals) < min_samples:
                reasons.append("CPU baseline or enough valid CPU samples are not available")
            if span < min_span:
                reasons.append("Observation window is too short")
            return WorkloadClassification("unknown", 0.0, reasons, "unknown", len(recent),
                metadata={"valid_cpu_samples": len(cpu_vals), "valid_memory_samples": len(mem_vals),
                          "observation_span_seconds": span})

        avg_cpu, avg_mem = sum(cpu_vals) / len(cpu_vals), sum(mem_vals) / len(mem_vals)
        max_cpu, max_mem = max(cpu_vals), max(mem_vals)
        available_ratios = [
            100.0 * sample.memory_available / sample.memory_total
            for sample in recent
            if sample.memory_available is not None and sample.memory_total
            and sample.memory_total > 0
        ]
        avg_available = sum(available_ratios) / len(available_ratios) if available_ratios else None
        quality = min(1.0, min(len(cpu_vals), len(mem_vals)) / max(min_samples, 1))
        evidence = [
            "CPU average {:.1f}% (peak {:.1f}%) over {} valid samples".format(avg_cpu, max_cpu, len(cpu_vals)),
            "Memory average {:.1f}% (peak {:.1f}%) over {} valid samples".format(avg_mem, max_mem, len(mem_vals)),
            "Observation span {:.1f}s; data quality {:.0f}%".format(span, quality * 100),
        ]
        if avg_available is not None:
            evidence.append("Available RAM averages {:.1f}% of installed memory".format(avg_available))
        cpu_heavy = avg_cpu >= self.config["cpu_heavy_threshold"]
        mem_heavy = (avg_mem >= self.config["memory_heavy_threshold"]
                     or (avg_available is not None and avg_available <= 10.0))
        cpu_light = avg_cpu <= self.config["cpu_light_threshold"]
        mem_light = avg_mem <= self.config["memory_light_threshold"]

        if cpu_heavy and mem_heavy:
            label, pressure = "combined", "high"
        elif cpu_heavy:
            label, pressure = "heavy_cpu", "high" if avg_cpu >= 95 else "medium"
        elif mem_heavy:
            label, pressure = "heavy_memory", "high" if avg_mem >= 95 else "medium"
        elif cpu_light and mem_light:
            label, pressure = "idle", "none"
        elif avg_cpu < 40 and avg_mem < 70:
            label, pressure = "light", "low"
        elif avg_cpu < 75 and avg_mem < 85:
            label, pressure = "normal_interactive", "low"
        else:
            label, pressure = "unknown", "medium"

        # Confidence is bounded and tied to completeness and number of observations.
        count_quality = min(1.0, len(recent) / max(min_samples * 2, 1))
        confidence = max(0.0, min(0.95, 0.55 * quality + 0.40 * count_quality))
        if self._last_classification and self._last_classification.classification != label:
            evidence.append("Workload changed from {}".format(self._last_classification.classification))
        result = WorkloadClassification(
            label, confidence, evidence, pressure, len(recent),
            metadata={"avg_cpu": avg_cpu, "avg_mem": avg_mem, "max_cpu": max_cpu,
                      "max_mem": max_mem, "avg_available_percent": avg_available,
                      "data_quality": quality, "observation_span_seconds": span},
        )
        self._last_classification = result
        return result

    def get_sustained_consumers(self, min_duration_seconds: int = 30) -> List[Dict]:
        """Return measured contributors with PID+creation-time identity, never PID-only targets."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=max(0, min_duration_seconds))
        consumers = []
        for key, samples in list(self._process_samples.items()):
            recent = [s for s in samples if cutoff <= s.timestamp <= now]
            if len(recent) < int(self.config["min_samples_for_sustained"]):
                continue
            span = (recent[-1].timestamp - recent[0].timestamp).total_seconds()
            if span < min_duration_seconds:
                continue
            cpu_vals = [s.cpu_percent for s in recent if s.cpu_percent is not None]
            mem_vals = [s.memory_rss for s in recent if s.memory_rss is not None]
            if not cpu_vals and not mem_vals:
                continue
            avg_cpu = sum(cpu_vals) / len(cpu_vals) if cpu_vals else None
            avg_mem = sum(mem_vals) / len(mem_vals) if mem_vals else None
            if not ((avg_cpu is not None and avg_cpu > 25) or
                    (avg_mem is not None and avg_mem > 300 * 1024 * 1024)):
                continue
            pid, created = key
            info = self._process_identities.get(key, {})
            identity = ProcessIdentity(pid, created, info.get("name") or recent[-1].name, info.get("exe"))
            consumers.append({
                "identity": identity, "pid": pid, "create_time": created,
                "name": identity.name, "username": info.get("username"), "avg_cpu": avg_cpu,
                "avg_memory_mb": avg_mem / (1024 * 1024) if avg_mem is not None else None,
                "sample_count": len(recent), "observation_span_seconds": span,
                "measurement_quality": min(1.0, len(recent) / max(3, self.config["min_samples_for_sustained"])),
                "latest_sample": recent[-1].timestamp,
            })
        return sorted(consumers, key=lambda item: (
            item["avg_memory_mb"] or 0, item["avg_cpu"] or 0), reverse=True)
