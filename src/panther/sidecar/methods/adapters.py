"""Conversion/serialization adapters for sidecar methods.

These adapters translate between internal service representations and the
JSON-RPC contract expected by the frontend. They contain no business logic,
only data transformation and platform-specific error handling.
"""

from __future__ import annotations

import hashlib
import platform
import socket
import time
from typing import Any, Dict, List, Optional

import psutil

from ...services import (
    app_inventory,
    history,
    process_adapter,
    recommendation_engine,
    startup_adapter,
    system_monitor,
)
from ...services.startup_adapter import UnsupportedPlatformError
from ...db import db


# ---------------------------------------------------------------------------
# Uptime / OS
# ---------------------------------------------------------------------------

def get_uptime() -> str:
    """Return human-readable system uptime (e.g., '3d 14h 22m')."""
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def get_operating_system() -> str:
    """Return OS name and release (e.g., 'Linux 6.8.0', 'Windows 11')."""
    system = platform.system()
    release = platform.release()
    return f"{system} {release}"


def get_hostname() -> str:
    """Return the system hostname."""
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Processes
# ---------------------------------------------------------------------------

def get_processes() -> List[Dict[str, Any]]:
    """Return process list matching frontend contract."""
    records = process_adapter.get_process_records()
    result = []
    for record in records:
        cpu = record.cpu_percent if record.cpu_percent is not None else 0.0
        if cpu < 0:
            cpu = 0.0
        memory_gb = round(record.memory_rss / (1024 ** 3), 2) if record.memory_rss else 0.0
        status = record.status or "unknown"
        status_lower = status.lower()
        if status_lower in ("running",):
            mapped_status = "running"
        elif status_lower in ("sleeping", "idle", "waiting", "locked"):
            mapped_status = "sleeping"
        elif status_lower in ("stopped", "zombie", "dead"):
            mapped_status = "stopped"
        else:
            mapped_status = "sleeping"  # default fallback
        result.append({
            "pid": record.identity.pid,
            "name": record.identity.name,
            "cpu": cpu,
            "memory": memory_gb,
            "status": mapped_status,
        })
    return result


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def _make_recommendation_id(category: str, issue: str) -> str:
    """Create a stable slug from category and issue."""
    raw = f"{category}:{issue}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _map_category(category: str) -> str:
    """Map engine category to frontend enum."""
    cat = category.lower()
    if cat in ("power",):
        return "battery"
    if cat in ("performance",):
        return "performance"
    if cat in ("storage",):
        return "storage"
    if cat in ("startup",):
        return "startup"
    if cat in ("security",):
        return "security"
    return "performance"  # default


def _map_level(impact: str, safety: str) -> str:
    """Map engine impact/safety to frontend level enum."""
    # Critical: high impact + unsafe
    if impact == "Critical" and safety != "High":
        return "critical"
    if impact == "High" and safety in ("Low", "Medium"):
        return "warning"
    if impact == "Critical":
        return "critical"
    if impact == "High":
        return "warning"
    return "normal"


def _map_action_target(category: str) -> str:
    """Map category to navigation target screen."""
    targets = {
        "performance": "Processes",
        "storage": "Storage",
        "battery": "Battery",
        "startup": "Startup Apps",
        "security": "Settings",
    }
    return targets.get(category, "Dashboard")


def get_recommendations() -> List[Dict[str, Any]]:
    """Return recommendations derived from real current metrics."""
    # Gather current metrics
    cpu = system_monitor.get_cpu_percent()
    ram = system_monitor.get_ram_usage()
    disk = get_disk_usage_platform()  # Use platform-aware default path
    battery = system_monitor.get_battery_info()

    metrics = {
        "cpu_percent": cpu,
        "ram_percent": ram.get("percent", 0),
        "disk_percent": disk.get("percent", 0),
        "battery_percent": battery.get("percent") if battery else None,
    }

    engine_recs = recommendation_engine.get_recommendations(metrics)
    result = []
    for rec in engine_recs:
        category = _map_category(rec.get("category", "Performance"))
        level = _map_level(
            rec.get("impact", "Low"),
            rec.get("safety", "High"),
        )
        action_target = rec.get("actionTarget") or _map_action_target(category)
        result.append({
            "id": _make_recommendation_id(category, rec.get("issue", "unknown")),
            "title": rec.get("issue", "Recommendation"),
            "description": rec.get("evidence") or rec.get("why", ""),
            "action": rec.get("action", ""),
            "actionTarget": action_target,
            "level": level,
            "category": category,
        })
    return result


# ---------------------------------------------------------------------------
# Activity History
# ---------------------------------------------------------------------------

def get_activity_history(limit: int = 100) -> List[Dict[str, Any]]:
    """Return recent activity logs matching frontend contract."""
    rows = history.get_recent(limit)
    result = []
    for row_id, ts, category, detail in rows:
        level = "info"
        cat_lower = category.lower()
        if cat_lower in ("error", "critical", "security"):
            level = "critical"
        elif cat_lower in ("warning", "action"):
            level = "warning"
        result.append({
            "id": row_id,
            "timestamp": ts,
            "level": level,
            "message": detail,
            "component": category,
        })
    return result


# ---------------------------------------------------------------------------
# Startup Apps (Windows only)
# ---------------------------------------------------------------------------

def get_startup_apps() -> List[Dict[str, Any]]:
    """Return startup entries matching frontend contract."""
    entries = startup_adapter.get_startup_entries()
    result = []
    for entry in entries:
        result.append({
            "name": entry.get("name", ""),
            "executable": entry.get("command", ""),
            "isEnabled": entry.get("enabled", True),
            "cpuImpact": None,  # not measured - honest null
            "memoryImpact": None,
        })
    return result


def set_startup_app_state(executable: str, enabled: bool) -> None:
    """Enable or disable a startup entry."""
    entries = startup_adapter.get_startup_entries()
    target = None
    for entry in entries:
        if entry.get("command") == executable or entry.get("name") == executable:
            target = entry
            break
    if not target:
        raise ValueError(f"Startup entry not found: {executable}")

    if enabled:
        # Not implemented on any platform currently
        raise NotImplementedError(
            "Enabling startup entries is not implemented. "
            "Callers should store the command before deletion."
        )
    else:
        startup_adapter.set_entry_enabled(target["name"], target["scope"], False)


# ---------------------------------------------------------------------------
# Installed Applications (Windows only, empty on other platforms)
# ---------------------------------------------------------------------------

def get_installed_applications() -> List[Dict[str, Any]]:
    """Return installed apps matching frontend contract."""
    apps = app_inventory.get_installed_apps()
    result = []
    for app in apps:
        result.append({
            "name": app.get("name") or "",
            "version": app.get("version") or "",
            "publisher": app.get("publisher") or "",
            "installDate": None,  # not available - honest null
            "cpuCores": None,     # not available - honest null
            "memoryMb": None,     # not available - honest null
        })
    return result


# ---------------------------------------------------------------------------
# Adaptive Control (persisted app preferences)
# ---------------------------------------------------------------------------

_ADAPTIVE_CONTROL_KEY = "adaptive_control.config"

_DEFAULT_ADAPTIVE_CONFIG = {
    "cpuThreshold": 85,
    "memoryThreshold": 90,
    "autoShutdown": False,
    "enabled": True,
    "aggressiveMode": False,
    "notifyOnAction": True,
}


def get_adaptive_control() -> Dict[str, Any]:
    """Return persisted adaptive control config with defaults."""
    stored = db.get_setting(_ADAPTIVE_CONTROL_KEY)
    if stored:
        try:
            import json
            config = json.loads(stored)
            # Merge with defaults to handle missing keys
            return {**_DEFAULT_ADAPTIVE_CONFIG, **config}
        except Exception:
            pass
    return _DEFAULT_ADAPTIVE_CONFIG.copy()


def set_adaptive_control(
    cpuThreshold: int,
    memoryThreshold: int,
    autoShutdown: bool,
    enabled: bool,
    aggressiveMode: bool,
    notifyOnAction: bool,
) -> Dict[str, Any]:
    """Validate and persist adaptive control config."""
    # Validate
    if not isinstance(cpuThreshold, (int, float)) or not (0 <= cpuThreshold <= 100):
        raise ValueError("cpuThreshold must be 0-100")
    if not isinstance(memoryThreshold, (int, float)) or not (0 <= memoryThreshold <= 100):
        raise ValueError("memoryThreshold must be 0-100")
    if not isinstance(autoShutdown, bool):
        raise ValueError("autoShutdown must be boolean")
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be boolean")
    if not isinstance(aggressiveMode, bool):
        raise ValueError("aggressiveMode must be boolean")
    if not isinstance(notifyOnAction, bool):
        raise ValueError("notifyOnAction must be boolean")

    config = {
        "cpuThreshold": int(cpuThreshold),
        "memoryThreshold": int(memoryThreshold),
        "autoShutdown": autoShutdown,
        "enabled": enabled,
        "aggressiveMode": aggressiveMode,
        "notifyOnAction": notifyOnAction,
    }
    import json
    db.set_setting(_ADAPTIVE_CONTROL_KEY, json.dumps(config))
    return config


# ---------------------------------------------------------------------------
# Settings (persisted app preferences)
# ---------------------------------------------------------------------------

_SETTINGS_KEY = "app.settings"

_DEFAULT_SETTINGS = {
    "theme": "system",
    "notifications": True,
    "autoStart": True,
    "updateCheck": True,
    "telemetry": False,
    "compactMode": False,
    "language": "en-US",
}


def get_settings() -> Dict[str, Any]:
    """Return persisted app settings with defaults."""
    stored = db.get_setting(_SETTINGS_KEY)
    if stored:
        try:
            import json
            config = json.loads(stored)
            return {**_DEFAULT_SETTINGS, **config}
        except Exception:
            pass
    return _DEFAULT_SETTINGS.copy()


def set_settings(
    theme: str,
    notifications: bool,
    autoStart: bool,
    updateCheck: bool,
    telemetry: bool,
    compactMode: bool,
    language: str,
) -> Dict[str, Any]:
    """Validate and persist app settings."""
    valid_themes = {"light", "dark", "system"}
    if theme not in valid_themes:
        raise ValueError(f"theme must be one of {valid_themes}")

    config = {
        "theme": theme,
        "notifications": bool(notifications),
        "autoStart": bool(autoStart),
        "updateCheck": bool(updateCheck),
        "telemetry": bool(telemetry),
        "compactMode": bool(compactMode),
        "language": str(language),
    }
    import json
    db.set_setting(_SETTINGS_KEY, json.dumps(config))
    return config


# ---------------------------------------------------------------------------
# Battery (enhanced with status field)
# ---------------------------------------------------------------------------

def get_battery_info_with_status() -> Dict[str, Any]:
    """Return battery info with derived status field."""
    batt = system_monitor.get_battery_info()
    if not batt:
        return {}
    percent = batt.get("percent", 0)
    power_plugged = batt.get("power_plugged", False)
    if power_plugged and percent >= 99.5:
        status = "full"
    elif power_plugged:
        status = "charging"
    else:
        status = "discharging"
    return {**batt, "status": status}


# ---------------------------------------------------------------------------
# Disk usage (platform-aware default path)
# ---------------------------------------------------------------------------

def get_disk_usage_platform(path: Optional[str] = None) -> Dict[str, Any]:
    """Return disk usage with platform-aware default path."""
    if path is None:
        path = "C:\\" if platform.system() == "Windows" else "/"
    return system_monitor.get_disk_usage(path)


# ---------------------------------------------------------------------------
# Directory listing (for storage exploration)
# ---------------------------------------------------------------------------

def list_directory(path: Optional[str] = None) -> Dict[str, Any]:
    """List a single directory (non-recursive) for storage explorer.
    
    If path is None, defaults to platform-appropriate root (C:\\ on Windows, / otherwise).
    """
    if path is None:
        path = "C:\\" if platform.system() == "Windows" else "/"
    from ...services.directory_browser import DirectoryBrowser
    browser = DirectoryBrowser()
    return browser.list_directory(path)