"""System monitoring service adapters.

Provides lightweight functions that wrap psutil (and, where needed, native Windows APIs) to fetch
CPU, RAM, disk and battery information. All calls are pure functions – they contain no
Qt or UI logic, satisfying the rule that business logic stays independent of the UI.
"""

import os
import psutil
from typing import Dict, Any, Optional

# Prime psutil's CPU counter so the first real reading is not a meaningless 0.0.
psutil.cpu_percent(interval=None)


def _default_disk_path() -> str:
    """System drive on Windows (honours non-C: installs); filesystem root elsewhere."""
    if os.name == "nt":
        return (os.environ.get("SystemDrive") or "C:") + "\\"
    return os.path.abspath(os.sep)


def get_cpu_percent() -> float:
    """Return CPU utilisation (0‑100) averaged since the previous call.

    Non-blocking: ``interval=None`` avoids freezing the UI thread for 100 ms on
    every refresh.
    """
    return psutil.cpu_percent(interval=None)

def get_ram_usage() -> Dict[str, Any]:
    """Return a mapping with total, available and used RAM (bytes) and usage percent."""
    vm = psutil.virtual_memory()
    return {
        "total": vm.total,
        "available": vm.available,
        "used": vm.used,
        "percent": vm.percent,
    }

def get_disk_usage(path: Optional[str] = None) -> Dict[str, Any]:
    """Return disk usage statistics for *path* (default: the system drive)."""
    du = psutil.disk_usage(path or _default_disk_path())
    return {
        "total": du.total,
        "used": du.used,
        "free": du.free,
        "percent": du.percent,
    }

def get_battery_info() -> Dict[str, Any]:
    """Return battery status if present, otherwise an empty dict.

    The dict contains *percent*, *secsleft*, *power_plugged* and *status* (a short
    human‑readable string). When psutil cannot find a battery, the dict is empty.
    """
    batt = psutil.sensors_battery()
    if batt is None:
        return {}
    return {
        "percent": batt.percent,
        "secsleft": batt.secsleft,
        "power_plugged": batt.power_plugged,
    }
