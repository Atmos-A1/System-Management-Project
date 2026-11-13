"""Unit tests for the frozen sidecar entrypoint's watchdog wiring."""

from __future__ import annotations

import sys
from unittest.mock import patch

from run_sidecar import _read_parent_pid_env, _start_parent_watchdog_if_frozen


def test_read_parent_pid_env_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("PANTHER_PARENT_PID", raising=False)
    assert _read_parent_pid_env() is None


def test_read_parent_pid_env_returns_none_when_empty(monkeypatch):
    monkeypatch.setenv("PANTHER_PARENT_PID", "")
    assert _read_parent_pid_env() is None


def test_read_parent_pid_env_parses_positive_pid(monkeypatch):
    monkeypatch.setenv("PANTHER_PARENT_PID", "4242")
    assert _read_parent_pid_env() == 4242


def test_read_parent_pid_env_strips_whitespace(monkeypatch):
    monkeypatch.setenv("PANTHER_PARENT_PID", "  4242\n")
    assert _read_parent_pid_env() == 4242


def test_read_parent_pid_env_rejects_garbage(monkeypatch):
    monkeypatch.setenv("PANTHER_PARENT_PID", "not-a-pid")
    assert _read_parent_pid_env() is None


def test_read_parent_pid_env_rejects_non_positive(monkeypatch):
    monkeypatch.setenv("PANTHER_PARENT_PID", "0")
    assert _read_parent_pid_env() is None
    monkeypatch.setenv("PANTHER_PARENT_PID", "-5")
    assert _read_parent_pid_env() is None
    monkeypatch.setenv("PANTHER_PARENT_PID", "1")
    assert _read_parent_pid_env() is None


def test_watchdog_not_started_when_not_frozen(monkeypatch):
    """Source checkouts must not start a watchdog that could kill the shell."""
    monkeypatch.delenv("PANTHER_PARENT_PID", raising=False)
    with patch.object(sys, "frozen", False, create=True), patch(
        "panther.sidecar.parent_watchdog.start_parent_watchdog"
    ) as mock_start:
        _start_parent_watchdog_if_frozen()
    mock_start.assert_not_called()


def test_watchdog_receives_explicit_parent_pid_when_frozen(monkeypatch):
    """The frozen sidecar forwards PANTHER_PARENT_PID to the watchdog."""
    monkeypatch.setenv("PANTHER_PARENT_PID", "4242")
    with patch.object(sys, "frozen", True, create=True), patch(
        "panther.sidecar.parent_watchdog.start_parent_watchdog"
    ) as mock_start:
        _start_parent_watchdog_if_frozen()
    mock_start.assert_called_once()
    assert mock_start.call_args.kwargs["parent_pid"] == 4242


def test_watchdog_swallows_errors_when_frozen(monkeypatch):
    """A watchdog failure must never abort sidecar startup."""
    monkeypatch.setenv("PANTHER_PARENT_PID", "4242")
    with patch.object(sys, "frozen", True, create=True), patch(
        "panther.sidecar.parent_watchdog.start_parent_watchdog",
        side_effect=RuntimeError("boom"),
    ):
        _start_parent_watchdog_if_frozen()  # must not raise
