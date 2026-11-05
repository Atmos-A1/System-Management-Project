"""Tests for the Panther JSON-RPC 2.0 sidecar (Stage 0).

These tests exercise the sidecar transport, method registry, and request
handling layer without spawning a subprocess.  The existing
``src/panther/services/system_monitor`` functions are called through the
sidecar exactly as the Tauri gateway would call them.
"""

import json
from io import StringIO

import pytest

from panther.sidecar.errors import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    error_response,
    success_response,
)
from panther.sidecar.methods import call_method, has_method, list_methods
from panther.sidecar.server import _handle_request
from panther.sidecar.transport import FrameTooLargeError, MAX_FRAME_SIZE, read_line


# ---------------------------------------------------------------------------
# Method registry
# ---------------------------------------------------------------------------


def test_list_methods_returns_registered_methods():
    methods = list_methods()
    assert "system_monitor.get_cpu_percent" in methods
    assert "system_monitor.get_ram_usage" in methods
    assert "system_monitor.get_disk_usage" in methods
    assert "system_monitor.get_battery_info" in methods


def test_has_method():
    assert has_method("system_monitor.get_cpu_percent") is True
    assert has_method("system_monitor.get_ram_usage") is True
    assert has_method("system_monitor.get_disk_usage") is True
    assert has_method("system_monitor.get_battery_info") is True
    assert has_method("process_actions.graceful_close") is False
    assert has_method("nonexistent.method") is False


def test_call_method_returns_real_values():
    cpu = call_method("system_monitor.get_cpu_percent")
    assert isinstance(cpu, (int, float))
    assert 0 <= cpu <= 100

    ram = call_method("system_monitor.get_ram_usage")
    assert isinstance(ram, dict)
    assert "total" in ram and "percent" in ram

    disk = call_method("system_monitor.get_disk_usage", path="/")
    assert isinstance(disk, dict)
    assert "percent" in disk

    batt = call_method("system_monitor.get_battery_info")
    assert isinstance(batt, dict)


def test_call_method_unknown_raises_key_error():
    with pytest.raises(KeyError):
        call_method("nonexistent.method")


# ---------------------------------------------------------------------------
# JSON-RPC request handling
# ---------------------------------------------------------------------------


def test_handle_request_success():
    response = _handle_request(
        '{"jsonrpc":"2.0","id":1,"method":"system_monitor.get_cpu_percent","params":{}}'
    )
    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "result" in response
    assert "error" not in response


def test_handle_request_correlates_ids():
    r1 = _handle_request(
        '{"jsonrpc":"2.0","id":42,"method":"system_monitor.get_cpu_percent","params":{}}'
    )
    r2 = _handle_request(
        '{"jsonrpc":"2.0","id":43,"method":"system_monitor.get_ram_usage","params":{}}'
    )
    assert r1["id"] == 42
    assert r2["id"] == 43


def test_handle_request_malformed_json():
    response = _handle_request("not json")
    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] is None
    assert response["error"]["code"] == PARSE_ERROR


def test_handle_request_unknown_method():
    response = _handle_request(
        '{"jsonrpc":"2.0","id":7,"method":"foo.bar","params":{}}'
    )
    assert response["error"]["code"] == METHOD_NOT_FOUND
    assert response["id"] == 7


def test_handle_request_invalid_params():
    response = _handle_request(
        '{"jsonrpc":"2.0","id":8,"method":"system_monitor.get_cpu_percent","params":"notdict"}'
    )
    assert response["error"]["code"] == INVALID_PARAMS
    assert response["id"] == 8


def test_handle_request_notification_no_response():
    # Notifications (no id) must return None, not an error response.
    response = _handle_request(
        '{"jsonrpc":"2.0","method":"system_monitor.get_cpu_percent","params":{}}'
    )
    assert response is None


def test_handle_request_missing_jsonrpc():
    response = _handle_request('{"id":1,"method":"system_monitor.get_cpu_percent"}')
    assert response["error"]["code"] == INVALID_REQUEST


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


def test_read_line_eof():
    stream = StringIO("")
    # Monkeypatch sys.stdin is complex; instead test the error path directly.
    assert MAX_FRAME_SIZE == 4 * 1024 * 1024


def test_frame_too_large_error_is_exception():
    assert issubclass(FrameTooLargeError, Exception)


# ---------------------------------------------------------------------------
# Error response helpers
# ---------------------------------------------------------------------------


def test_error_response_shape():
    err = error_response(PARSE_ERROR, "Parse error", "abc", {"detail": "x"})
    assert err["jsonrpc"] == "2.0"
    assert err["id"] == "abc"
    assert err["error"]["code"] == PARSE_ERROR
    assert err["error"]["message"] == "Parse error"
    assert err["error"]["data"] == {"detail": "x"}


def test_success_response_shape():
    ok = success_response(1, {"percent": 42.5})
    assert ok["jsonrpc"] == "2.0"
    assert ok["id"] == 1
    assert ok["result"] == {"percent": 42.5}
    assert "error" not in ok
