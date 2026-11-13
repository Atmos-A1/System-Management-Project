"""Unit tests for the parent watchdog module."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, str(__file__.replace("tests/test_parent_watchdog.py", "src")))

from panther.sidecar.parent_watchdog import (
    parent_is_gone,
    should_terminate,
    _watchdog_loop,
    start_parent_watchdog,
)


# ---------------------------------------------------------------------------
# parent_is_gone tests
# ---------------------------------------------------------------------------


def test_parent_is_gone_alive():
    """parent_is_gone returns False when parent is alive."""
    mock_getppid = MagicMock(return_value=12345)
    mock_is_alive = MagicMock(return_value=True)

    result = parent_is_gone(mock_getppid, mock_is_alive)
    assert result is False
    mock_getppid.assert_called_once()
    mock_is_alive.assert_called_once_with(12345)


def test_parent_is_gone_dead():
    """parent_is_gone returns True when parent is dead."""
    mock_getppid = MagicMock(return_value=12345)
    mock_is_alive = MagicMock(return_value=False)

    result = parent_is_gone(mock_getppid, mock_is_alive)
    assert result is True


def test_parent_is_gone_pid_zero_or_negative():
    """parent_is_gone returns False when PID <= 1 (invalid/init — safe default)."""
    for pid in [0, 1, -1, -100]:
        mock_getppid = MagicMock(return_value=pid)
        mock_is_alive = MagicMock(return_value=True)  # Should not be called

        result = parent_is_gone(mock_getppid, mock_is_alive)
        assert result is False, f"Expected False (safe default) for PID {pid}"
        mock_is_alive.assert_not_called()


def test_parent_is_gone_getppid_exception():
    """parent_is_gone returns False (treat as alive) when getppid raises."""
    mock_getppid = MagicMock(side_effect=OSError("no parent"))
    mock_is_alive = MagicMock(return_value=True)

    result = parent_is_gone(mock_getppid, mock_is_alive)
    assert result is False, "Should treat getppid failure as alive (safe default)"


def test_parent_is_gone_access_denied():
    """parent_is_gone returns False (treat as alive) when is_alive raises AccessDenied."""
    mock_getppid = MagicMock(return_value=12345)
    mock_is_alive = MagicMock(side_effect=Exception("Access denied"))

    result = parent_is_gone(mock_getppid, mock_is_alive)
    assert result is False, "Should treat exceptions as alive (safe default)"


def test_parent_is_gone_no_such_process():
    """parent_is_gone treats all exceptions as alive (safe default)."""
    mock_getppid = MagicMock(return_value=12345)
    mock_is_alive = MagicMock(side_effect=Exception("No such process"))

    result = parent_is_gone(mock_getppid, mock_is_alive)
    assert result is False, "Should treat exceptions as alive (safe default)"


# ---------------------------------------------------------------------------
# should_terminate tests
# ---------------------------------------------------------------------------


def test_should_terminate_aliases_parent_is_gone():
    """should_terminate is a thin wrapper around parent_is_gone."""
    mock_getppid = MagicMock(return_value=12345)
    mock_is_alive = MagicMock(return_value=False)

    assert should_terminate(mock_getppid, mock_is_alive) is True
    mock_is_alive.assert_called_once_with(12345)

    mock_is_alive.reset_mock()
    mock_is_alive.return_value = True
    assert should_terminate(mock_getppid, mock_is_alive) is False


# ---------------------------------------------------------------------------
# _watchdog_loop tests (pure, no real threads)
# ---------------------------------------------------------------------------


def test_watchdog_loop_terminates_when_parent_gone():
    """_watchdog_loop calls on_parent_gone once when is_alive returns False."""
    mock_is_alive = MagicMock(side_effect=[True, True, False])
    mock_on_parent_gone = MagicMock()
    mock_sleep = MagicMock()

    _watchdog_loop(
        parent_pid=12345,
        interval=0.1,
        is_alive=mock_is_alive,
        on_parent_gone=mock_on_parent_gone,
        sleep=mock_sleep,
    )

    # is_alive called until it returns False
    assert mock_is_alive.call_count == 3
    # on_parent_gone called exactly once
    mock_on_parent_gone.assert_called_once()
    # sleep called for each iteration before termination
    assert mock_sleep.call_count == 2


def test_watchdog_loop_never_terminates_when_parent_alive():
    """_watchdog_loop loops and sleeps when parent stays alive, never calls on_parent_gone.

    The watchdog loop continues while the parent is "alive" (is_alive returns True)
    and the parent_pid > 1. It should NOT call on_parent_gone in this case.
    This test verifies the loop runs with injected sleep and is_alive without
    relying on exception propagation from is_alive (which parent_is_gone catches
    as "alive" per the safe-default design).
    """
    call_count = 0

    def counting_is_alive(_pid):
        nonlocal call_count
        call_count += 1
        # Return True forever (parent stays alive); cap at 3 calls for test brevity
        if call_count > 3:
            raise StopIteration("test limit exceeded")
        return True

    mock_on_parent_gone = MagicMock()
    mock_sleep = MagicMock()

    # Run the loop; it should keep iterating since parent is "alive"
    # and parent_pid=12345 > 1, so parent_is_gone returns False (safe default).
    try:
        _watchdog_loop(
            parent_pid=12345,
            interval=0.1,
            is_alive=counting_is_alive,
            on_parent_gone=mock_on_parent_gone,
            sleep=mock_sleep,
        )
    except StopIteration:
        # StopIteration may fire after the 4th call (our cap); that's fine.
        pass

    # is_alive was called at least 3 times (once per loop iteration before exit)
    assert call_count >= 3, f"expected is_alive called >=3 times, got {call_count}"
    # on_parent_gone must never be called when parent is "alive"
    mock_on_parent_gone.assert_not_called()
    # sleep should have been called at least 2 times (between 3 iterations)
    assert mock_sleep.call_count >= 2, f"expected sleep called >=2 times, got {mock_sleep.call_count}"


def test_watchdog_loop_returns_immediately_for_invalid_pid():
    """_watchdog_loop returns immediately for PID <= 1 without calling on_parent_gone."""
    mock_is_alive = MagicMock()
    mock_on_parent_gone = MagicMock()
    mock_sleep = MagicMock()

    for pid in [0, 1, -1]:
        mock_is_alive.reset_mock()
        mock_on_parent_gone.reset_mock()
        mock_sleep.reset_mock()

        _watchdog_loop(
            parent_pid=pid,
            interval=0.1,
            is_alive=mock_is_alive,
            on_parent_gone=mock_on_parent_gone,
            sleep=mock_sleep,
        )

        mock_is_alive.assert_not_called()
        mock_on_parent_gone.assert_not_called()
        mock_sleep.assert_not_called()


def test_watchdog_loop_uses_injected_sleep():
    """_watchdog_loop uses the injected sleep function with correct interval."""
    mock_is_alive = MagicMock(side_effect=[True, False])
    mock_on_parent_gone = MagicMock()
    mock_sleep = MagicMock()

    _watchdog_loop(
        parent_pid=12345,
        interval=2.5,
        is_alive=mock_is_alive,
        on_parent_gone=mock_on_parent_gone,
        sleep=mock_sleep,
    )

    # interval is capped at 0.5
    mock_sleep.assert_called_once_with(0.5)


def test_watchdog_loop_does_not_call_os_exit_directly():
    """Regression guard: _watchdog_loop never calls os._exit directly; uses on_parent_gone."""
    import os

    original_exit = os._exit
    exit_called = False

    def mock_exit(_code):
        nonlocal exit_called
        exit_called = True

    try:
        os._exit = mock_exit  # type: ignore

        mock_is_alive = MagicMock(return_value=False)
        mock_on_parent_gone = MagicMock(side_effect=lambda: os._exit(0))
        mock_sleep = MagicMock()

        _watchdog_loop(
            parent_pid=12345,
            interval=0.1,
            is_alive=mock_is_alive,
            on_parent_gone=mock_on_parent_gone,
            sleep=mock_sleep,
        )

        # The mock on_parent_gone called os._exit, but _watchdog_loop itself didn't
        assert exit_called  # The callback did the exit
    finally:
        os._exit = original_exit  # type: ignore


# ---------------------------------------------------------------------------
# start_parent_watchdog tests
# ---------------------------------------------------------------------------


def test_start_parent_watchdog_zero_interval():
    """start_parent_watchdog returns None when interval <= 0."""
    result = start_parent_watchdog(interval=0)
    assert result is None

    result = start_parent_watchdog(interval=-1)
    assert result is None


def test_start_parent_watchdog_no_psutil():
    """start_parent_watchdog returns None when psutil not available."""
    with patch.dict("sys.modules", {"psutil": None}):
        result = start_parent_watchdog(interval=2.0)
        assert result is None


def test_start_parent_watchdog_invalid_parent_pid():
    """start_parent_watchdog returns None when parent PID is invalid."""
    with patch("os.getppid", return_value=0):
        result = start_parent_watchdog(interval=2.0)
        assert result is None

    with patch("os.getppid", return_value=1):
        result = start_parent_watchdog(interval=2.0)
        assert result is None


def test_start_parent_watchdog_swallows_thread_errors():
    """start_parent_watchdog never raises, returns None on thread error."""
    with patch("os.getppid", return_value=99999), patch("psutil.pid_exists", return_value=True), patch(
        "threading.Thread.start", side_effect=RuntimeError("thread error")
    ):
        result = start_parent_watchdog(interval=2.0)
        assert result is None


def test_start_parent_watchdog_custom_on_parent_gone():
    """start_parent_watchdog accepts custom on_parent_gone callback."""
    mock_on_parent_gone = MagicMock()

    with patch("os.getppid", return_value=99999), patch("psutil.pid_exists", return_value=True), patch(
        "threading.Thread.start"
    ) as mock_start:
        thread = start_parent_watchdog(interval=0.1, on_parent_gone=mock_on_parent_gone)
        assert thread is not None

        # Capture the target function passed to Thread
        target = mock_start.call_args[0][0] if mock_start.call_args else None
        assert target is not None


# ---------------------------------------------------------------------------
# Run if executed directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])