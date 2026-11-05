#!/usr/bin/env python3
"""Capture Phase 4 screens in both appearances at supported window sizes.

Deterministic service doubles are installed on the screen modules only; no
production service, worker or contract is changed.

Usage:
    QT_QPA_PLATFORM=offscreen PYTHONPATH=src python tools/ui_phase4_shots.py
"""

import os
import sys
import time
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

import panther.ui.adaptive_control as adaptive_module  # noqa: E402
import panther.ui.battery as battery_module  # noqa: E402
import panther.ui.processes as processes_module  # noqa: E402
from panther.domain.models import ProcessIdentity, ProcessRecord  # noqa: E402
from panther.domain.models.policy import PolicyRecommendation  # noqa: E402
from panther.domain.models.workload import WorkloadClassification  # noqa: E402
from panther.ui.adaptive_control import AdaptiveControlScreen  # noqa: E402
from panther.ui.battery import BatteryScreen  # noqa: E402
from panther.ui.processes import ProcessesScreen  # noqa: E402
from panther.ui.theme import ThemeManager  # noqa: E402

OUT_DIR = os.environ.get("PHASE4_SHOT_DIR", "/tmp/opencode/phase4-shots")
SIZES = ((1240, 820), (1000, 700), (900, 600))


def _record(pid, name, cpu, memory):
    return ProcessRecord(
        identity=ProcessIdentity(pid, 100.0 + pid, name, r"C:\Apps\{}".format(name)),
        ppid=1,
        username="tester",
        status="running",
        cpu_percent=cpu,
        memory_rss=memory,
        memory_vms=memory * 2,
        num_threads=4,
        first_seen=datetime.now(timezone.utc),
    )


def _processes():
    return [
        _record(101, "Panther.exe", 8.4, 420 * 1024**2),
        _record(102, "Report Viewer.exe", 3.1, 260 * 1024**2),
        _record(103, "Secure Notes.exe", 1.2, 180 * 1024**2),
        _record(104, "Cloud Sync.exe", 6.7, 310 * 1024**2),
        _record(105, "Media Player.exe", 2.5, 150 * 1024**2),
    ]


def _classify(process):
    return {
        "category": "User application",
        "risk_level": "Medium",
        "confidence": 0.7,
        "explanation": "User-installed application with a verified executable "
        "path and no critical system association.",
        "evidence": ["Executable outside system directories"],
        "can_terminate": False,
    }


def _snapshot():
    return {
        "system": SimpleNamespace(
            cpu_percent=24.6,
            memory_percent=61.2,
            memory_available=6 * 1024**3,
            timestamp=datetime.now(timezone.utc),
        ),
        "workload": WorkloadClassification(
            "heavy_memory", 0.88, ["measured memory pressure"], "high", 12,
            datetime.now(timezone.utc),
        ),
        "recommendations": [
            PolicyRecommendation(
                id="rec-1",
                action_type="investigate",
                target_pid=None,
                target_name=None,
                reason="Sustained memory pressure",
                explanation="Review high-memory applications. Panther will not "
                "close or change anything automatically.",
                confidence=0.88,
                measurement_quality=0.91,
                evidence=["measured memory pressure", "sustained for 12 samples"],
            )
        ],
        "applications": [
            {"pid": 101, "name": "Panther.exe", "cpu": 8.4,
             "memory": 420 * 1024**2, "category": "User application"},
            {"pid": 104, "name": "Cloud Sync.exe", "cpu": 6.7,
             "memory": 310 * 1024**2, "category": "User application"},
            {"pid": 102, "name": "Report Viewer.exe", "cpu": 3.1,
             "memory": 260 * 1024**2, "category": "User application"},
        ],
    }


def _processes_screen(loader=None):
    screen = ProcessesScreen(process_loader=loader or _processes)
    screen.killTimer(screen.refresh_timer)
    deadline = time.time() + 5
    while screen.table.state == "loading" and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    QApplication.processEvents()
    if screen.proxy.rowCount():
        screen.table.selectRow(0)
    QApplication.processEvents()
    return screen


def _adaptive_screen():
    screen = AdaptiveControlScreen()
    screen._refresh_timer.stop()
    screen.refresh = lambda: None
    screen.mode.setCurrentIndex(1)
    screen._on_sample_ready(_snapshot())
    return screen


def _battery_screen():
    screen = BatteryScreen()
    screen.timer.stop()
    return screen


def install_doubles():
    processes_module.ProcessClassifier.classify = lambda self, process: _classify(process)

    battery_module.get_battery_status = lambda: {
        "percent": 72,
        "secsleft": 8100,
        "power_plugged": False,
    }
    battery_module.get_processes = _processes_dicts
    battery_module.classify_process = lambda process: {
        "category": "User application",
        "risk_level": "Medium",
        "explanation": "User-installed application.",
        "can_terminate": process.get("pid") != 4,
    }


def _processes_dicts():
    return [
        {"pid": 101, "name": "Panther.exe", "cpu_percent": 8.4,
         "memory_rss": 420 * 1024**2},
        {"pid": 104, "name": "Cloud Sync.exe", "cpu_percent": 6.7,
         "memory_rss": 310 * 1024**2},
        {"pid": 4, "name": "System", "cpu_percent": 0.0,
         "memory_rss": 1024 * 1024},
    ]


def build_screens():
    return (
        ("processes", _processes_screen()),
        ("adaptive", _adaptive_screen()),
        ("battery", _battery_screen()),
    )


def capture(app, name, screen, width=1000, height=700):
    screen.show()
    screen.resize(width, height)
    app.processEvents()
    app.processEvents()
    theme = ThemeManager.current_theme()
    path = os.path.join(OUT_DIR, f"{name}-{theme}-{width}x{height}.png")
    screen.grab().save(path)
    print(path)
    screen.hide()
    app.processEvents()


def capture_state_screens(app):
    capture(app, "processes-empty", _processes_screen(loader=lambda: []), 1000, 700)

    def failing_loader():
        raise OSError("The process provider did not respond")

    capture(app, "processes-error", _processes_screen(loader=failing_loader), 1000, 700)

    adaptive_empty = AdaptiveControlScreen()
    adaptive_empty._refresh_timer.stop()
    adaptive_empty.refresh = lambda: None
    adaptive_empty.mode.setCurrentIndex(1)
    adaptive_empty._on_sample_ready({
        "system": None,
        "workload": WorkloadClassification(
            "unknown", 0.0, ["insufficient observations"], "unknown", 0,
            datetime.now(timezone.utc),
        ),
        "recommendations": [],
        "applications": [],
    })
    capture(app, "adaptive-empty", adaptive_empty, 1000, 700)

    battery_module.get_battery_status = lambda: {}
    capture(app, "battery-unsupported", _battery_screen(), 1000, 700)


def main() -> int:
    install_doubles()
    os.makedirs(OUT_DIR, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)

    for theme in ("light", "dark"):
        ThemeManager.apply_theme(app, theme)
        app.processEvents()
        screens = build_screens()
        for name, screen in screens:
            for width, height in SIZES:
                capture(app, name, screen, width, height)
        capture_state_screens(app)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
