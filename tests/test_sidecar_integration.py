"""End-to-end integration test for the Panther sidecar.

Spawns the actual Python sidecar process via `python -m panther.sidecar.server`
with PYTHONPATH set, sends JSON-RPC 2.0 requests for all frontend method names,
and verifies responses match expected shapes.

This is REAL integration testing - no mocks for the sidecar process itself.
"""

import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

import pytest


# Path to the src directory (contains panther package)
SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
SRC_DIR = os.path.abspath(SRC_DIR)


class SidecarProcess:
    """Manages a sidecar subprocess for integration testing."""

    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.request_id = 0

    def start(self):
        """Start the sidecar process."""
        env = os.environ.copy()
        env["PYTHONPATH"] = SRC_DIR
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "panther.sidecar.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,  # line buffered
        )
        # Wait for startup message
        time.sleep(0.5)
        # Drain any startup diagnostics from stderr
        self._drain_stderr()

    def _drain_stderr(self):
        """Drain stderr non-blocking."""
        if self.proc and self.proc.stderr:
            try:
                # Read available stderr lines
                import select
                while True:
                    ready, _, _ = select.select([self.proc.stderr], [], [], 0.01)
                    if not ready:
                        break
                    line = self.proc.stderr.readline()
                    if not line:
                        break
                    print(f"[sidecar stderr] {line.strip()}", file=sys.stderr)
            except (ImportError, OSError):
                pass  # select not available or other issue

    def stop(self):
        """Stop the sidecar process."""
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            self.proc = None

    def call(self, method: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Send a JSON-RPC request and return the parsed response."""
        if not self.proc or not self.proc.stdin or not self.proc.stdout:
            raise RuntimeError("Sidecar not started")

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {},
        }

        # Send request
        request_line = json.dumps(request, separators=(",", ":")) + "\n"
        self.proc.stdin.write(request_line)
        self.proc.stdin.flush()

        # Read response
        response_line = self.proc.stdout.readline()
        if not response_line:
            # Check stderr for diagnostics
            self._drain_stderr()
            raise RuntimeError(f"No response from sidecar for method {method}")

        response = json.loads(response_line.strip())
        return response

    def notify(self, method: str, params: Optional[Dict] = None):
        """Send a JSON-RPC notification (no response expected)."""
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("Sidecar not started")

        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        request_line = json.dumps(request, separators=(",", ":")) + "\n"
        self.proc.stdin.write(request_line)
        self.proc.stdin.flush()


@pytest.fixture(scope="module")
def sidecar():
    """Module-scoped sidecar process fixture."""
    proc = SidecarProcess()
    proc.start()
    yield proc
    proc.stop()


# ---------------------------------------------------------------------------
# Test all frontend-expected methods
# ---------------------------------------------------------------------------

def test_method_system_monitor_get_cpu_percent(sidecar):
    response = sidecar.call("system_monitor.get_cpu_percent", {})
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "result" in response
    assert "error" not in response
    cpu = response["result"]
    assert isinstance(cpu, (int, float))
    assert 0 <= cpu <= 100


def test_method_system_monitor_get_ram_usage(sidecar):
    response = sidecar.call("system_monitor.get_ram_usage", {})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    ram = response["result"]
    assert isinstance(ram, dict)
    assert "total" in ram
    assert "available" in ram
    assert "used" in ram
    assert "percent" in ram
    assert all(isinstance(v, (int, float)) for v in ram.values())
    assert 0 <= ram["percent"] <= 100


def test_method_system_monitor_get_disk_usage(sidecar):
    # Test with explicit path
    response = sidecar.call("system_monitor.get_disk_usage", {"path": "/"})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    disk = response["result"]
    assert isinstance(disk, dict)
    assert "total" in disk
    assert "used" in disk
    assert "free" in disk
    assert "percent" in disk
    assert all(isinstance(v, (int, float)) for v in disk.values())
    assert 0 <= disk["percent"] <= 100


def test_method_system_monitor_get_disk_usage_default_path(sidecar):
    # Test without path (should use platform-aware default)
    response = sidecar.call("system_monitor.get_disk_usage", {})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    disk = response["result"]
    assert isinstance(disk, dict)
    assert "percent" in disk


def test_method_system_monitor_get_battery_info(sidecar):
    response = sidecar.call("system_monitor.get_battery_info", {})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    battery = response["result"]
    assert isinstance(battery, dict)
    # May be empty (no battery) or have keys
    if battery:
        assert "percent" in battery
        assert "secsleft" in battery
        assert "power_plugged" in battery
        assert "status" in battery  # NEW: status field
        assert battery["status"] in ("charging", "discharging", "full")


def test_method_system_monitor_uptime(sidecar):
    response = sidecar.call("system_monitor.uptime", {})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    uptime = response["result"]
    assert isinstance(uptime, str)
    assert uptime.endswith("m")
    # Format like "3d 14h 22m" or "14h 22m" or "22m"
    parts = uptime.split()
    assert all(p.endswith(("d", "h", "m")) for p in parts)


def test_method_system_monitor_operating_system(sidecar):
    response = sidecar.call("system_monitor.operating_system", {})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    os_str = response["result"]
    assert isinstance(os_str, str)
    # Should be like "Linux 6.8.0" or "Windows 11"
    assert " " in os_str


def test_method_system_monitor_hostname(sidecar):
    response = sidecar.call("system_monitor.hostname", {})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    hostname = response["result"]
    assert isinstance(hostname, str)
    assert len(hostname) > 0


def test_method_system_monitor_get_processes(sidecar):
    response = sidecar.call("system_monitor.get_processes", {})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    processes = response["result"]
    assert isinstance(processes, list)
    if processes:
        proc = processes[0]
        assert "pid" in proc
        assert isinstance(proc["pid"], int)
        assert "name" in proc
        assert isinstance(proc["name"], str)
        assert "cpu" in proc
        assert isinstance(proc["cpu"], (int, float))
        assert proc["cpu"] >= 0
        assert "memory" in proc
        assert isinstance(proc["memory"], (int, float))
        assert proc["memory"] >= 0
        assert "status" in proc
        assert proc["status"] in ("running", "sleeping", "stopped")


def test_method_system_monitor_get_recommendations(sidecar):
    response = sidecar.call("system_monitor.get_recommendations", {})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    recs = response["result"]
    assert isinstance(recs, list)
    for rec in recs:
        assert "id" in rec
        assert isinstance(rec["id"], str)
        assert len(rec["id"]) == 16  # SHA1 truncated
        assert "title" in rec
        assert isinstance(rec["title"], str)
        assert "description" in rec
        assert isinstance(rec["description"], str)
        assert "action" in rec
        assert isinstance(rec["action"], str)
        assert "actionTarget" in rec
        assert isinstance(rec["actionTarget"], str)
        assert "level" in rec
        assert rec["level"] in ("normal", "warning", "critical")
        assert "category" in rec
        assert rec["category"] in ("performance", "storage", "battery", "startup", "security")


def test_method_system_monitor_get_activity_history(sidecar):
    response = sidecar.call("system_monitor.get_activity_history", {})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    history = response["result"]
    assert isinstance(history, list)
    for entry in history:
        assert "id" in entry
        assert isinstance(entry["id"], int)
        assert "timestamp" in entry
        assert isinstance(entry["timestamp"], str)
        assert "level" in entry
        assert entry["level"] in ("info", "warning", "critical")
        assert "message" in entry
        assert isinstance(entry["message"], str)
        assert "component" in entry
        assert isinstance(entry["component"], str)


def test_method_system_monitor_get_activity_history_with_limit(sidecar):
    response = sidecar.call("system_monitor.get_activity_history", {"limit": 10})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    history = response["result"]
    assert isinstance(history, list)
    assert len(history) <= 10


def test_method_system_monitor_get_startup_apps(sidecar):
    response = sidecar.call("system_monitor.get_startup_apps", {})
    assert response["jsonrpc"] == "2.0"
    # On Linux, this should return SERVICE_UNAVAILABLE (-32000)
    if "error" in response:
        assert response["error"]["code"] == -32000
        assert "Unsupported on this platform" in response["error"]["message"]
    else:
        apps = response["result"]
        assert isinstance(apps, list)
        for app in apps:
            assert "name" in app
            assert "executable" in app
            assert "isEnabled" in app
            assert isinstance(app["isEnabled"], bool)
            # cpuImpact and memoryImpact should be null (honest)
            assert "cpuImpact" in app
            assert app["cpuImpact"] is None
            assert "memoryImpact" in app
            assert app["memoryImpact"] is None


def test_method_system_monitor_set_startup_app_state(sidecar):
    # First get the list to find an executable (or test error handling)
    get_response = sidecar.call("system_monitor.get_startup_apps", {})

    if "error" in get_response:
        # On Linux, should get unsupported error for both enable and disable
        disable_response = sidecar.call("system_monitor.set_startup_app_state", {
            "executable": "nonexistent.exe",
            "enabled": False,
        })
        assert "error" in disable_response
        assert disable_response["error"]["code"] == -32000
        assert "Unsupported on this platform" in disable_response["error"]["message"]

        enable_response = sidecar.call("system_monitor.set_startup_app_state", {
            "executable": "nonexistent.exe",
            "enabled": True,
        })
        assert "error" in enable_response
        assert enable_response["error"]["code"] == -32000
        assert "Unsupported on this platform" in enable_response["error"]["message"]
    else:
        apps = get_response["result"]
        if apps:
            exe = apps[0]["executable"]
            # Test disable (should work on Windows)
            disable_response = sidecar.call("system_monitor.set_startup_app_state", {
                "executable": exe,
                "enabled": False,
            })
            assert "jsonrpc" in disable_response

            # Test enable - should return -32000 (NotImplementedError)
            enable_response = sidecar.call("system_monitor.set_startup_app_state", {
                "executable": exe,
                "enabled": True,
            })
            assert "error" in enable_response
            assert enable_response["error"]["code"] == -32000
            assert "Unsupported on this platform" in enable_response["error"]["message"]
        else:
            # No apps to test with
            pass


def test_method_system_monitor_get_installed_applications(sidecar):
    response = sidecar.call("system_monitor.get_installed_applications", {})
    assert response["jsonrpc"] == "2.0"
    # On Linux, returns empty list (not unsupported - just no data)
    if "error" in response:
        # Could be unsupported on some platforms
        assert response["error"]["code"] == -32000
    else:
        apps = response["result"]
        assert isinstance(apps, list)
        for app in apps:
            assert "name" in app
            assert "version" in app
            assert "publisher" in app
            # installDate, cpuCores, memoryMb should be null (honest)
            assert "installDate" in app
            assert app["installDate"] is None
            assert "cpuCores" in app
            assert app["cpuCores"] is None
            assert "memoryMb" in app
            assert app["memoryMb"] is None


def test_method_system_monitor_get_adaptive_control(sidecar):
    response = sidecar.call("system_monitor.get_adaptive_control", {})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    config = response["result"]
    assert isinstance(config, dict)
    expected_keys = ["cpuThreshold", "memoryThreshold", "autoShutdown", "enabled", "aggressiveMode", "notifyOnAction"]
    for key in expected_keys:
        assert key in config
    assert isinstance(config["cpuThreshold"], int)
    assert 0 <= config["cpuThreshold"] <= 100
    assert isinstance(config["memoryThreshold"], int)
    assert 0 <= config["memoryThreshold"] <= 100
    assert isinstance(config["autoShutdown"], bool)
    assert isinstance(config["enabled"], bool)
    assert isinstance(config["aggressiveMode"], bool)
    assert isinstance(config["notifyOnAction"], bool)


def test_method_system_monitor_set_adaptive_control(sidecar):
    response = sidecar.call("system_monitor.set_adaptive_control", {
        "cpuThreshold": 80,
        "memoryThreshold": 85,
        "autoShutdown": True,
        "enabled": False,
        "aggressiveMode": True,
        "notifyOnAction": False,
    })
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    config = response["result"]
    assert config["cpuThreshold"] == 80
    assert config["memoryThreshold"] == 85
    assert config["autoShutdown"] is True
    assert config["enabled"] is False
    assert config["aggressiveMode"] is True
    assert config["notifyOnAction"] is False

    # Verify it persists
    get_response = sidecar.call("system_monitor.get_adaptive_control", {})
    assert get_response["result"] == config


def test_method_system_monitor_set_adaptive_control_validation(sidecar):
    # Test invalid cpuThreshold
    response = sidecar.call("system_monitor.set_adaptive_control", {
        "cpuThreshold": 150,  # Invalid
        "memoryThreshold": 90,
        "autoShutdown": False,
        "enabled": True,
        "aggressiveMode": False,
        "notifyOnAction": True,
    })
    assert "error" in response
    assert response["error"]["code"] == -32602  # INVALID_PARAMS


def test_method_system_monitor_get_settings(sidecar):
    response = sidecar.call("system_monitor.get_settings", {})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    settings = response["result"]
    assert isinstance(settings, dict)
    expected_keys = ["theme", "notifications", "autoStart", "updateCheck", "telemetry", "compactMode", "language"]
    for key in expected_keys:
        assert key in settings
    assert settings["theme"] in ("light", "dark", "system")
    assert isinstance(settings["notifications"], bool)
    assert isinstance(settings["autoStart"], bool)
    assert isinstance(settings["updateCheck"], bool)
    assert isinstance(settings["telemetry"], bool)
    assert isinstance(settings["compactMode"], bool)
    assert isinstance(settings["language"], str)


def test_method_system_monitor_set_settings(sidecar):
    response = sidecar.call("system_monitor.set_settings", {
        "theme": "dark",
        "notifications": False,
        "autoStart": True,
        "updateCheck": False,
        "telemetry": True,
        "compactMode": True,
        "language": "de-DE",
    })
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    settings = response["result"]
    assert settings["theme"] == "dark"
    assert settings["notifications"] is False
    assert settings["language"] == "de-DE"

    # Verify it persists
    get_response = sidecar.call("system_monitor.get_settings", {})
    assert get_response["result"] == settings


def test_method_system_monitor_set_settings_validation(sidecar):
    # Test invalid theme
    response = sidecar.call("system_monitor.set_settings", {
        "theme": "invalid",
        "notifications": True,
        "autoStart": True,
        "updateCheck": True,
        "telemetry": False,
        "compactMode": False,
        "language": "en-US",
    })
    assert "error" in response
    assert response["error"]["code"] == -32602  # INVALID_PARAMS


def test_method_system_monitor_list_directory(sidecar):
    response = sidecar.call("system_monitor.list_directory", {"path": "/"})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    listing = response["result"]
    assert isinstance(listing, dict)
    assert "path" in listing
    assert "entries" in listing
    assert "errors" in listing
    assert "truncated" in listing
    assert "limit" in listing
    assert "cancelled" in listing
    assert "error" in listing
    assert isinstance(listing["entries"], list)
    assert isinstance(listing["errors"], list)
    assert isinstance(listing["truncated"], bool)
    assert isinstance(listing["limit"], int)
    assert isinstance(listing["cancelled"], bool)
    if listing["entries"]:
        entry = listing["entries"][0]
        assert "name" in entry
        assert "path" in entry
        assert "type" in entry
        assert entry["type"] in ("directory", "file", "link", "reparse", "other")
        assert "size" in entry
        assert "modified" in entry
        assert "is_dir" in entry
        assert "is_file" in entry
        assert "is_link" in entry
        assert "is_reparse" in entry
        assert "is_hidden" in entry


def test_method_system_monitor_list_directory_default_path(sidecar):
    # Test without path (should use platform-aware default)
    response = sidecar.call("system_monitor.list_directory", {})
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    listing = response["result"]
    assert isinstance(listing, dict)
    assert "path" in listing
    assert "entries" in listing
    assert isinstance(listing["entries"], list)


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

def test_method_not_found(sidecar):
    response = sidecar.call("nonexistent.method", {})
    assert response["jsonrpc"] == "2.0"
    assert "error" in response
    assert response["error"]["code"] == -32601  # METHOD_NOT_FOUND


def test_invalid_params(sidecar):
    # params must be dict or absent
    request = {
        "jsonrpc": "2.0",
        "id": 999,
        "method": "system_monitor.get_cpu_percent",
        "params": "not a dict",
    }
    sidecar.proc.stdin.write(json.dumps(request) + "\n")
    sidecar.proc.stdin.flush()
    response_line = sidecar.proc.stdout.readline()
    response = json.loads(response_line.strip())
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 999
    assert "error" in response
    assert response["error"]["code"] == -32602  # INVALID_PARAMS
    assert "Invalid params" in response["error"]["message"]


def test_notification_no_response(sidecar):
    # Notifications have no id and should get no response
    sidecar.notify("system_monitor.get_cpu_percent", {})
    # Should not block waiting for response
    time.sleep(0.1)
    # Sidecar should still be alive and responsive
    response = sidecar.call("system_monitor.get_cpu_percent", {})
    assert "result" in response


if __name__ == "__main__":
    pytest.main([__file__, "-v"])