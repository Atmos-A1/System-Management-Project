"""Process discovery adapters backed by psutil.

The typed ``get_process_records`` API is the preferred interface. The legacy
``get_processes`` and ``get_process_details`` dictionary APIs remain available
while existing UI and service callers are migrated in later phases.
"""

from datetime import datetime, timezone
import math
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import psutil
except Exception:  # pragma: no cover - exercised when psutil is unavailable
    psutil = None

from ..domain.models import ProcessIdentity, ProcessRecord


class _CpuSampler:
    """Calculate non-blocking CPU percentages from consecutive CPU-time samples."""

    def __init__(self) -> None:
        self._samples: Dict[Tuple[int, float], Tuple[float, float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _total_cpu_time(cpu_times: Any) -> Optional[float]:
        if cpu_times is None:
            return None
        try:
            total = float(cpu_times.user) + float(cpu_times.system)
        except (AttributeError, TypeError, ValueError):
            return None
        if not math.isfinite(total) or total < 0:
            return None
        return total

    def sample(self, identity: ProcessIdentity, cpu_times: Any,
               sampled_at: Optional[float] = None) -> Optional[float]:
        total = self._total_cpu_time(cpu_times)
        if total is None:
            return None
        now = time.monotonic() if sampled_at is None else sampled_at
        key = identity.key
        with self._lock:
            previous = self._samples.get(key)
            self._samples[key] = (total, now)
            # Bound the cache and discard the previous PID incarnation.
            for old_key in tuple(self._samples):
                if old_key[0] == identity.pid and old_key != key:
                    self._samples.pop(old_key, None)
            if previous is None:
                return None
            previous_total, previous_time = previous
            elapsed = now - previous_time
            delta = total - previous_total
            if elapsed <= 0 or delta < 0:
                return None
            value = (delta / elapsed) * 100.0
            return value if math.isfinite(value) else None

    def retain(self, active_keys) -> None:
        """Drop samples for processes absent from the latest full snapshot."""
        active = set(active_keys)
        with self._lock:
            self._samples = {
                key: value for key, value in self._samples.items() if key in active
            }


_cpu_sampler = _CpuSampler()
_first_seen_by_identity: Dict[Tuple[int, float], datetime] = {}
_first_seen_lock = threading.Lock()


def _first_seen(identity: ProcessIdentity) -> datetime:
    with _first_seen_lock:
        return _first_seen_by_identity.setdefault(identity.key, datetime.now(timezone.utc))


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result >= 0 else None


def _memory_value(memory_info: Any, attribute: str) -> Optional[int]:
    if memory_info is None:
        return None
    return _optional_int(getattr(memory_info, attribute, None))


def _record_from_info(info: Dict[str, Any], sampled_at: Optional[float] = None) -> ProcessRecord:
    pid = _optional_int(info.get("pid"))
    create_time = info.get("create_time")
    name = info.get("name")
    if pid is None:
        raise ValueError("Process PID is unavailable")
    if isinstance(create_time, bool) or not isinstance(create_time, (int, float)):
        raise ValueError("Process creation time is unavailable")
    if not math.isfinite(float(create_time)) or float(create_time) <= 0:
        raise ValueError("Process creation time is invalid")
    if not isinstance(name, str) or not name.strip():
        name = "process-{}".format(pid)

    exe = info.get("exe")
    if not isinstance(exe, str) or not exe:
        exe = None

    identity = ProcessIdentity(
        pid=pid,
        create_time=float(create_time),
        name=name,
        exe=exe,
    )
    cpu_times = info.get("cpu_times")
    if cpu_times is not None:
        # The first CPU-time observation establishes a baseline and is
        # deliberately reported as unavailable, not as 0% idle.
        cpu_percent = _cpu_sampler.sample(identity, cpu_times, sampled_at)
    else:
        cpu_percent = None

    memory_info = info.get("memory_info")
    return ProcessRecord(
        identity=identity,
        ppid=_optional_int(info.get("ppid")),
        username=info.get("username") if isinstance(info.get("username"), str) else None,
        status=info.get("status") if isinstance(info.get("status"), str) else None,
        cpu_percent=cpu_percent,
        memory_rss=_memory_value(memory_info, "rss"),
        memory_vms=_memory_value(memory_info, "vms"),
        num_threads=_optional_int(info.get("num_threads")),
        first_seen=_first_seen(identity),
    )



def iter_process_records():
    """Yield typed process records incrementally from one psutil enumeration.

    The iterator avoids building a second full list before the UI can display
    rows. Cache pruning occurs only after a complete enumeration; early
    cancellation does not incorrectly discard still-active process baselines.
    """
    if psutil is None:
        raise RuntimeError("psutil is required for process enumeration")
    attrs = [
        "pid", "name", "cpu_times", "memory_info", "ppid", "exe",
        "username", "create_time", "status", "num_threads",
    ]
    active_keys = []
    completed = False
    try:
        for process in psutil.process_iter(attrs):
            try:
                record = _record_from_info(process.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess,
                    KeyError, TypeError, ValueError):
                continue
            except Exception:
                continue
            active_keys.append(record.identity.key)
            yield record
        completed = True
    finally:
        if completed:
            _cpu_sampler.retain(active_keys)
            active = set(active_keys)
            with _first_seen_lock:
                for key in tuple(_first_seen_by_identity):
                    if key not in active:
                        _first_seen_by_identity.pop(key, None)


def _collect_process_records(include_legacy_metadata: bool = False):
    """Collect typed snapshots and optional metadata for legacy callers.

    Processes without a usable PID or creation time are skipped because a
    ProcessIdentity cannot safely be constructed for them. One inaccessible or
    disappearing process does not prevent other processes from being returned.
    """
    if psutil is None:
        raise RuntimeError("psutil is required for process enumeration")

    records: List[ProcessRecord] = []
    attrs = [
        "pid", "name", "cpu_times", "memory_info", "ppid", "exe",
        "username", "create_time", "status", "num_threads",
    ]
    if include_legacy_metadata:
        attrs.append("cmdline")
    legacy_metadata = {}
    for process in psutil.process_iter(attrs):
        try:
            info = process.info
            record = _record_from_info(info)
            records.append(record)
            if include_legacy_metadata:
                command_line = info.get("cmdline") or []
                legacy_metadata[record.identity.key] = " ".join(
                    str(part) for part in command_line
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, KeyError, TypeError, ValueError):
            continue
        except Exception:
            # Keep discovery resilient to unexpected per-process API failures.
            continue
    active_keys = [record.identity.key for record in records]
    _cpu_sampler.retain(active_keys)
    active = set(active_keys)
    with _first_seen_lock:
        for key in tuple(_first_seen_by_identity):
            if key not in active:
                _first_seen_by_identity.pop(key, None)
    return records, legacy_metadata


def get_process_records() -> List[ProcessRecord]:
    """Return typed process snapshots; unavailable fields are represented by None."""
    records, _ = _collect_process_records()
    return records


def _record_to_legacy_dict(record: ProcessRecord) -> Dict[str, Any]:
    """Translate a typed record to the dictionary shape used by old callers."""
    create_time = record.identity.create_time
    try:
        start_time = datetime.fromtimestamp(create_time).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        start_time = None
    return {
        "pid": record.identity.pid,
        "ppid": record.ppid,
        "name": record.identity.name,
        "exe": record.identity.exe or "",
        "cmdline": "",
        "username": record.username or "",
        # Legacy callers expect numbers. New code should use get_process_records
        # and preserve None as unavailable.
        "cpu_percent": record.cpu_percent if record.cpu_percent is not None else 0.0,
        "memory_rss": record.memory_rss if record.memory_rss is not None else 0,
        "memory_vms": record.memory_vms if record.memory_vms is not None else 0,
        "status": record.status or "",
        "create_time": create_time,
        "start_time": start_time,
        "num_threads": record.num_threads,
    }


def get_processes() -> List[Dict[str, Any]]:
    """Legacy dictionary API retained during migration to ProcessRecord."""
    records, legacy_metadata = _collect_process_records(include_legacy_metadata=True)
    processes = []
    for record in records:
        process = _record_to_legacy_dict(record)
        process["cmdline"] = legacy_metadata.get(record.identity.key, "")
        processes.append(process)
    return processes


def get_process_tree() -> tuple:
    """Build a process tree using the legacy dictionary representation."""
    processes = get_processes()
    tree = {}
    process_map = {process["pid"]: process for process in processes}
    for process in processes:
        parent_pid = process.get("ppid") or 0
        tree.setdefault(parent_pid, []).append(process)
    return tree, process_map


def get_process_details(pid: int) -> Dict[str, Any]:
    """Legacy detailed dictionary API; retained for existing callers."""
    if psutil is None:
        raise RuntimeError("psutil is required")
    try:
        process = psutil.Process(pid)
        memory_info = process.memory_info()
        create_time = process.create_time()
        try:
            start_time = datetime.fromtimestamp(create_time).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            start_time = None

        def read_or_none(method_name: str):
            try:
                return getattr(process, method_name)()
            except (psutil.AccessDenied, psutil.NoSuchProcess, AttributeError):
                return None

        cpu_times = read_or_none("cpu_times")
        identity = ProcessIdentity(
            pid=process.pid,
            create_time=create_time,
            name=process.name() or "process-{}".format(pid),
            exe=read_or_none("exe") or None,
        )
        cpu_percent = _cpu_sampler.sample(identity, cpu_times) if cpu_times is not None else None
        return {
            "pid": process.pid,
            "ppid": read_or_none("ppid"),
            "name": identity.name,
            "exe": identity.exe or "",
            "cmdline": " ".join(read_or_none("cmdline") or []),
            "username": read_or_none("username") or "",
            "cpu_percent": cpu_percent if cpu_percent is not None else 0.0,
            "memory_rss": getattr(memory_info, "rss", None),
            "memory_vms": getattr(memory_info, "vms", None),
            "status": read_or_none("status") or "",
            "create_time": create_time,
            "start_time": start_time,
            "num_threads": read_or_none("num_threads"),
            "cwd": read_or_none("cwd") or "",
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        raise
