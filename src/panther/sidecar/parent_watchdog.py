"""Parent process watchdog for PyInstaller onefile sidecar.

Prevents orphaned child processes when the Tauri parent is killed (e.g., via
Task Manager, crash, or forced termination). The watchdog runs as a daemon
thread and calls `on_parent_gone()` when the parent process disappears.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Callable, Optional


def parent_is_gone(getppid: Callable[[], int], is_alive: Callable[[int], bool]) -> bool:
    """Check if the parent process is gone.

    Pure helper with no side effects — testable without threading or time.

    Args:
        getppid: Callable returning the parent PID (typically `os.getppid`).
        is_alive: Callable taking a PID and returning True if the process exists
            (typically `psutil.pid_exists`).

    Returns:
        True if the parent process is confirmed gone, False otherwise.
    """
    try:
        ppid = getppid()
    except Exception:
        # If we can't get the parent PID, treat as alive (safe default — never kill on uncertainty)
        return False

    # Invalid or init PID — treat as alive (safe default)
    if ppid <= 1:
        return False

    try:
        return not is_alive(ppid)
    except Exception:
        # Any error (including AccessDenied) — treat as alive to avoid false exits
        return False


def should_terminate(
    getppid: Callable[[], int],
    is_alive: Callable[[int], bool],
) -> bool:
    """Pure function: returns True if the watchdog should terminate the process.

    This is a thin wrapper around `parent_is_gone` for semantic clarity in the loop.
    """
    return parent_is_gone(getppid, is_alive)


def _watchdog_loop(
    parent_pid: int,
    interval: float,
    is_alive: Callable[[int], bool],
    on_parent_gone: Callable[[], None],
    sleep: Callable[[float], None],
) -> None:
    """Watchdog loop with all collaborators injected.

    Args:
        parent_pid: The parent PID to monitor (captured at startup).
        interval: Polling interval in seconds.
        is_alive: Callable taking a PID, returning True if process exists.
        on_parent_gone: Callback invoked exactly once when parent is gone.
        sleep: Callable taking seconds to sleep (e.g., `time.sleep`).
    """
    if parent_pid <= 1:
        return

    while True:
        if should_terminate(lambda: parent_pid, is_alive):
            on_parent_gone()
            return
        sleep(min(interval, 0.5))


def start_parent_watchdog(
    interval: float = 2.0,
    *,
    on_parent_gone: Optional[Callable[[], None]] = None,
) -> threading.Thread | None:
    """Start a daemon thread that exits the process when the parent disappears.

    Args:
        interval: Polling interval in seconds. If <= 0, the watchdog is not started.
        on_parent_gone: Callback when parent dies. Defaults to `os._exit(0)`.

    Returns:
        The started thread, or None if not started (interval <= 0 or error).
    """
    if interval <= 0:
        return None

    try:
        import psutil
    except Exception:
        # psutil not available — cannot run watchdog
        return None

    # Capture parent PID once at startup
    try:
        parent_pid = os.getppid()
    except Exception:
        return None

    if parent_pid <= 1:
        return None

    if on_parent_gone is None:
        on_parent_gone = lambda: os._exit(0)

    def _runner() -> None:
        _watchdog_loop(
            parent_pid=parent_pid,
            interval=interval,
            is_alive=psutil.pid_exists,
            on_parent_gone=on_parent_gone,
            sleep=time.sleep,
        )

    try:
        thread = threading.Thread(target=_runner, daemon=True, name="panther-parent-watchdog")
        thread.start()
        return thread
    except Exception:
        # Never fail startup due to watchdog thread issues
        return None