"""Unit tests for sidecar method adapters."""

import json
import platform
import time
from unittest.mock import MagicMock, patch

import pytest

from panther.sidecar.methods.adapters import (
    get_uptime,
    get_operating_system,
    get_hostname,
    get_processes,
    get_recommendations,
    get_activity_history,
    get_startup_apps,
    set_startup_app_state,
    get_installed_applications,
    get_adaptive_control,
    set_adaptive_control,
    get_settings,
    set_settings,
    get_battery_info_with_status,
    get_disk_usage_platform,
    list_directory,
    _DEFAULT_ADAPTIVE_CONFIG,
    _DEFAULT_SETTINGS,
    _make_recommendation_id,
    _map_category,
    _map_level,
    _map_action_target,
)


# ---------------------------------------------------------------------------
# Uptime / OS
# ---------------------------------------------------------------------------

def test_get_uptime_returns_string():
    result = get_uptime()
    assert isinstance(result, str)
    assert result.endswith("m")
    # Format: "Xd Yh Zm" or "Yh Zm" or "Zm"
    parts = result.split()
    assert all(p.endswith(("d", "h", "m")) for p in parts)


def test_get_operating_system_returns_string():
    result = get_operating_system()
    assert isinstance(result, str)
    expected = f"{platform.system()} {platform.release()}"
    assert result == expected


def test_get_hostname_returns_string():
    result = get_hostname()
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# Process mapping
# ---------------------------------------------------------------------------

@patch("panther.sidecar.methods.adapters.process_adapter.get_process_records")
def test_get_processes_maps_fields_correctly(mock_get_records):
    mock_record = MagicMock()
    mock_record.identity.pid = 1234
    mock_record.identity.name = "test_process"
    mock_record.cpu_percent = 15.5
    mock_record.memory_rss = 1024 * 1024 * 1024  # 1 GB
    mock_record.status = "running"

    mock_get_records.return_value = [mock_record]

    result = get_processes()
    assert len(result) == 1
    proc = result[0]
    assert proc["pid"] == 1234
    assert proc["name"] == "test_process"
    assert proc["cpu"] == 15.5
    assert proc["memory"] == 1.0  # 1 GB rounded
    assert proc["status"] == "running"


@patch("panther.sidecar.methods.adapters.process_adapter.get_process_records")
def test_get_processes_maps_sleeping_status(mock_get_records):
    mock_record = MagicMock()
    mock_record.identity.pid = 5678
    mock_record.identity.name = "sleeping_proc"
    mock_record.cpu_percent = 0.0
    mock_record.memory_rss = 512 * 1024 * 1024  # 0.5 GB
    mock_record.status = "sleeping"

    mock_get_records.return_value = [mock_record]

    result = get_processes()
    assert result[0]["status"] == "sleeping"


@patch("panther.sidecar.methods.adapters.process_adapter.get_process_records")
def test_get_processes_maps_stopped_status(mock_get_records):
    mock_record = MagicMock()
    mock_record.identity.pid = 9999
    mock_record.identity.name = "stopped_proc"
    mock_record.cpu_percent = None  # First sample
    mock_record.memory_rss = 100 * 1024 * 1024
    mock_record.status = "stopped"

    mock_get_records.return_value = [mock_record]

    result = get_processes()
    assert result[0]["status"] == "stopped"
    assert result[0]["cpu"] == 0.0  # None -> 0.0


@patch("panther.sidecar.methods.adapters.process_adapter.get_process_records")
def test_get_processes_clamps_negative_cpu(mock_get_records):
    mock_record = MagicMock()
    mock_record.identity.pid = 1111
    mock_record.identity.name = "negative_cpu"
    mock_record.cpu_percent = -5.0  # Should be clamped to 0.0
    mock_record.memory_rss = 0
    mock_record.status = "running"

    mock_get_records.return_value = [mock_record]

    result = get_processes()
    assert result[0]["cpu"] == 0.0


# ---------------------------------------------------------------------------
# Recommendations mapping
# ---------------------------------------------------------------------------

def test_make_recommendation_id_stable():
    id1 = _make_recommendation_id("performance", "High CPU")
    id2 = _make_recommendation_id("performance", "High CPU")
    assert id1 == id2
    assert len(id1) == 16  # SHA1 truncated to 16 chars


def test_map_category():
    assert _map_category("Power") == "battery"
    assert _map_category("Performance") == "performance"
    assert _map_category("Storage") == "storage"
    assert _map_category("Startup") == "startup"
    assert _map_category("Security") == "security"
    assert _map_category("Unknown") == "performance"  # default


def test_map_level():
    assert _map_level("Critical", "Low") == "critical"
    assert _map_level("Critical", "High") == "critical"
    assert _map_level("High", "Medium") == "warning"
    assert _map_level("High", "High") == "warning"
    assert _map_level("Medium", "High") == "normal"
    assert _map_level("Low", "High") == "normal"


def test_map_action_target():
    assert _map_action_target("performance") == "Processes"
    assert _map_action_target("storage") == "Storage"
    assert _map_action_target("battery") == "Battery"
    assert _map_action_target("startup") == "Startup Apps"
    assert _map_action_target("security") == "Settings"
    assert _map_action_target("unknown") == "Dashboard"


@patch("panther.sidecar.methods.adapters.system_monitor.get_cpu_percent")
@patch("panther.sidecar.methods.adapters.system_monitor.get_ram_usage")
@patch("panther.sidecar.methods.adapters.system_monitor.get_disk_usage")
@patch("panther.sidecar.methods.adapters.system_monitor.get_battery_info")
@patch("panther.sidecar.methods.adapters.recommendation_engine.get_recommendations")
def test_get_recommendations_derives_from_real_metrics(
    mock_rec_engine, mock_battery, mock_disk, mock_ram, mock_cpu
):
    mock_cpu.return_value = 90.0
    mock_ram.return_value = {"percent": 95.0}
    mock_disk.return_value = {"percent": 50.0}
    mock_battery.return_value = {"percent": 50, "power_plugged": False}
    mock_rec_engine.return_value = [
        {
            "issue": "High CPU usage",
            "evidence": "CPU at 90%",
            "why": "High CPU slows system",
            "action": "Check processes",
            "confidence": 0.9,
            "impact": "High",
            "safety": "Medium",
            "category": "Performance",
        }
    ]

    result = get_recommendations()

    assert len(result) == 1
    rec = result[0]
    assert rec["title"] == "High CPU usage"
    assert rec["description"] == "CPU at 90%"
    assert rec["action"] == "Check processes"
    assert rec["level"] == "warning"  # High impact, Medium safety -> warning
    assert rec["category"] == "performance"
    assert rec["actionTarget"] == "Processes"
    assert len(rec["id"]) == 16


# ---------------------------------------------------------------------------
# Activity History mapping
# ---------------------------------------------------------------------------

@patch("panther.sidecar.methods.adapters.history.get_recent")
def test_get_activity_history_maps_fields(mock_get_recent):
    mock_get_recent.return_value = [
        (1, "2024-01-15T10:30:00", "action", "User clicked button"),
        (2, "2024-01-15T10:31:00", "error", "Failed to connect"),
        (3, "2024-01-15T10:32:00", "metric", "CPU spike detected"),
    ]

    result = get_activity_history(3)

    assert len(result) == 3
    assert result[0] == {
        "id": 1,
        "timestamp": "2024-01-15T10:30:00",
        "level": "warning",  # action -> warning
        "message": "User clicked button",
        "component": "action",
    }
    assert result[1]["level"] == "critical"  # error -> critical
    assert result[2]["level"] == "info"  # metric -> info


# ---------------------------------------------------------------------------
# Startup Apps
# ---------------------------------------------------------------------------

@patch("panther.sidecar.methods.adapters.startup_adapter.get_startup_entries")
def test_get_startup_apps_maps_fields(mock_get_entries):
    mock_get_entries.return_value = [
        {"name": "TestApp", "command": "C:\\Test\\app.exe", "scope": "HKCU", "enabled": True},
    ]

    result = get_startup_apps()
    assert len(result) == 1
    app = result[0]
    assert app["name"] == "TestApp"
    assert app["executable"] == "C:\\Test\\app.exe"
    assert app["isEnabled"] is True
    assert app["cpuImpact"] is None
    assert app["memoryImpact"] is None


@patch("panther.sidecar.methods.adapters.startup_adapter.get_startup_entries")
@patch("panther.sidecar.methods.adapters.startup_adapter.set_entry_enabled")
def test_set_startup_app_state_disables(mock_set_enabled, mock_get_entries):
    mock_get_entries.return_value = [
        {"name": "TestApp", "command": "C:\\Test\\app.exe", "scope": "HKCU", "enabled": True},
    ]

    set_startup_app_state("C:\\Test\\app.exe", False)

    mock_set_enabled.assert_called_once_with("TestApp", "HKCU", False)


@patch("panther.sidecar.methods.adapters.startup_adapter.get_startup_entries")
def test_set_startup_app_state_enable_raises_not_implemented(mock_get_entries):
    mock_get_entries.return_value = [
        {"name": "TestApp", "command": "C:\\Test\\app.exe", "scope": "HKCU", "enabled": False},
    ]

    with pytest.raises(NotImplementedError):
        set_startup_app_state("C:\\Test\\app.exe", True)


@patch("panther.sidecar.methods.adapters.startup_adapter.get_startup_entries")
def test_set_startup_app_state_not_found_raises(mock_get_entries):
    mock_get_entries.return_value = []

    with pytest.raises(ValueError, match="not found"):
        set_startup_app_state("nonexistent.exe", False)


# ---------------------------------------------------------------------------
# Installed Applications
# ---------------------------------------------------------------------------

@patch("panther.sidecar.methods.adapters.app_inventory.get_installed_apps")
def test_get_installed_applications_maps_fields(mock_get_apps):
    mock_get_apps.return_value = [
        {"name": "TestApp", "version": "1.0.0", "publisher": "TestCorp", "install_location": "C:\\Test"},
    ]

    result = get_installed_applications()
    assert len(result) == 1
    app = result[0]
    assert app["name"] == "TestApp"
    assert app["version"] == "1.0.0"
    assert app["publisher"] == "TestCorp"
    assert app["installDate"] is None
    assert app["cpuCores"] is None
    assert app["memoryMb"] is None


# ---------------------------------------------------------------------------
# Adaptive Control persistence
# ---------------------------------------------------------------------------

@patch("panther.sidecar.methods.adapters.db.get_setting")
@patch("panther.sidecar.methods.adapters.db.set_setting")
def test_get_adaptive_control_returns_defaults_when_empty(mock_set, mock_get):
    mock_get.return_value = None

    result = get_adaptive_control()

    assert result == _DEFAULT_ADAPTIVE_CONFIG


@patch("panther.sidecar.methods.adapters.db.get_setting")
@patch("panther.sidecar.methods.adapters.db.set_setting")
def test_get_adaptive_control_merges_with_defaults(mock_set, mock_get):
    mock_get.return_value = json.dumps({"cpuThreshold": 75})

    result = get_adaptive_control()

    assert result["cpuThreshold"] == 75
    assert result["memoryThreshold"] == _DEFAULT_ADAPTIVE_CONFIG["memoryThreshold"]
    assert result["enabled"] == _DEFAULT_ADAPTIVE_CONFIG["enabled"]


@patch("panther.sidecar.methods.adapters.db.get_setting")
@patch("panther.sidecar.methods.adapters.db.set_setting")
def test_set_adaptive_control_validates_and_persists(mock_set, mock_get):
    mock_get.return_value = None

    result = set_adaptive_control(
        cpuThreshold=80,
        memoryThreshold=85,
        autoShutdown=True,
        enabled=False,
        aggressiveMode=True,
        notifyOnAction=False,
    )

    assert result["cpuThreshold"] == 80
    assert result["memoryThreshold"] == 85
    assert result["autoShutdown"] is True
    assert result["enabled"] is False
    assert result["aggressiveMode"] is True
    assert result["notifyOnAction"] is False

    # Verify persistence
    mock_set.assert_called_once()
    stored_key, stored_value = mock_set.call_args[0]
    assert stored_key == "adaptive_control.config"
    stored_config = json.loads(stored_value)
    assert stored_config == result


def test_set_adaptive_control_rejects_invalid_cpu_threshold():
    with pytest.raises(ValueError, match="cpuThreshold must be 0-100"):
        set_adaptive_control(
            cpuThreshold=150,
            memoryThreshold=90,
            autoShutdown=False,
            enabled=True,
            aggressiveMode=False,
            notifyOnAction=True,
        )


def test_set_adaptive_control_rejects_invalid_memory_threshold():
    with pytest.raises(ValueError, match="memoryThreshold must be 0-100"):
        set_adaptive_control(
            cpuThreshold=85,
            memoryThreshold=-10,
            autoShutdown=False,
            enabled=True,
            aggressiveMode=False,
            notifyOnAction=True,
        )


def test_set_adaptive_control_rejects_non_boolean():
    with pytest.raises(ValueError, match="autoShutdown must be boolean"):
        set_adaptive_control(
            cpuThreshold=85,
            memoryThreshold=90,
            autoShutdown="yes",
            enabled=True,
            aggressiveMode=False,
            notifyOnAction=True,
        )


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

@patch("panther.sidecar.methods.adapters.db.get_setting")
def test_get_settings_returns_defaults_when_empty(mock_get):
    mock_get.return_value = None

    result = get_settings()

    assert result == _DEFAULT_SETTINGS


@patch("panther.sidecar.methods.adapters.db.get_setting")
def test_get_settings_merges_with_defaults(mock_get):
    mock_get.return_value = json.dumps({"theme": "dark", "compactMode": True})

    result = get_settings()

    assert result["theme"] == "dark"
    assert result["compactMode"] is True
    assert result["notifications"] == _DEFAULT_SETTINGS["notifications"]


@patch("panther.sidecar.methods.adapters.db.set_setting")
def test_set_settings_validates_and_persists(mock_set):
    result = set_settings(
        theme="dark",
        notifications=False,
        autoStart=True,
        updateCheck=False,
        telemetry=True,
        compactMode=True,
        language="de-DE",
    )

    assert result["theme"] == "dark"
    assert result["notifications"] is False
    assert result["language"] == "de-DE"

    mock_set.assert_called_once()
    stored_key, stored_value = mock_set.call_args[0]
    assert stored_key == "app.settings"
    stored_config = json.loads(stored_value)
    assert stored_config == result


def test_set_settings_rejects_invalid_theme():
    with pytest.raises(ValueError, match="theme must be one of"):
        set_settings(
            theme="invalid",
            notifications=True,
            autoStart=True,
            updateCheck=True,
            telemetry=False,
            compactMode=False,
            language="en-US",
        )


# ---------------------------------------------------------------------------
# Battery status derivation
# ---------------------------------------------------------------------------

@patch("panther.sidecar.methods.adapters.system_monitor.get_battery_info")
def test_get_battery_info_with_status_charging(mock_get_battery):
    mock_get_battery.return_value = {"percent": 80, "secsleft": 3600, "power_plugged": True}

    result = get_battery_info_with_status()

    assert result["percent"] == 80
    assert result["status"] == "charging"


@patch("panther.sidecar.methods.adapters.system_monitor.get_battery_info")
def test_get_battery_info_with_status_full(mock_get_battery):
    mock_get_battery.return_value = {"percent": 100, "secsleft": -1, "power_plugged": True}

    result = get_battery_info_with_status()

    assert result["status"] == "full"


@patch("panther.sidecar.methods.adapters.system_monitor.get_battery_info")
def test_get_battery_info_with_status_discharging(mock_get_battery):
    mock_get_battery.return_value = {"percent": 50, "secsleft": 7200, "power_plugged": False}

    result = get_battery_info_with_status()

    assert result["status"] == "discharging"


@patch("panther.sidecar.methods.adapters.system_monitor.get_battery_info")
def test_get_battery_info_with_status_empty(mock_get_battery):
    mock_get_battery.return_value = {}

    result = get_battery_info_with_status()

    assert result == {}


# ---------------------------------------------------------------------------
# Disk usage platform-aware default
# ---------------------------------------------------------------------------

@patch("panther.sidecar.methods.adapters.system_monitor.get_disk_usage")
def test_get_disk_usage_platform_windows_default(mock_get_usage):
    with patch("panther.sidecar.methods.adapters.platform.system", return_value="Windows"):
        get_disk_usage_platform()
        mock_get_usage.assert_called_once_with("C:\\")


@patch("panther.sidecar.methods.adapters.system_monitor.get_disk_usage")
def test_get_disk_usage_platform_linux_default(mock_get_usage):
    with patch("panther.sidecar.methods.adapters.platform.system", return_value="Linux"):
        get_disk_usage_platform()
        mock_get_usage.assert_called_once_with("/")


@patch("panther.sidecar.methods.adapters.system_monitor.get_disk_usage")
def test_get_disk_usage_platform_explicit_path(mock_get_usage):
    get_disk_usage_platform("/home")
    mock_get_usage.assert_called_once_with("/home")


# ---------------------------------------------------------------------------
# Directory listing
# ---------------------------------------------------------------------------

@patch("panther.services.directory_browser.DirectoryBrowser")
def test_list_directory_calls_browser(mock_browser_class):
    mock_browser = MagicMock()
    mock_browser.list_directory.return_value = {"path": "/test", "entries": []}
    mock_browser_class.return_value = mock_browser

    result = list_directory("/test")

    assert result == {"path": "/test", "entries": []}
    mock_browser.list_directory.assert_called_once_with("/test")