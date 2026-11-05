#!/usr/bin/env python3
"""Capture Phase 3 screens in both appearances at supported window sizes.

Deterministic service doubles are installed on the screen modules only; no
production service, worker or contract is changed.

Usage:
    QT_QPA_PLATFORM=offscreen PYTHONPATH=src python tools/ui_phase3_shots.py
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

import panther.ui.applications as applications_module  # noqa: E402
import panther.ui.dashboard as dashboard_module  # noqa: E402
import panther.ui.history as history_module  # noqa: E402
import panther.ui.startup as startup_module  # noqa: E402
from panther.ui.applications import ApplicationsScreen  # noqa: E402
from panther.ui.dashboard import DashboardScreen  # noqa: E402
from panther.ui.history import HistoryScreen  # noqa: E402
from panther.ui.startup import StartupScreen  # noqa: E402
from panther.ui.theme import ThemeManager  # noqa: E402

OUT_DIR = os.environ.get("PHASE3_SHOT_DIR", "/tmp/opencode/phase3-shots")
SIZES = ((1240, 820), (1000, 700), (900, 600))

_CPU = [18.4, 24.1, 21.7, 29.3, 26.5, 31.2, 27.8, 33.4]
_RAM = [31.2, 33.8, 36.4, 34.1, 38.7, 35.2, 39.1, 36.8]
_DISK = [80.5, 80.6, 80.8, 81.0, 81.1, 81.3, 81.4, 81.6]
_BATTERY = [64, 63, 62, 61, 60, 59, 58, 57]
_cpu_index = [0]
_ram_index = [0]
_disk_index = [0]
_battery_index = [0]


def _next(sequence, counter):
    value = sequence[min(counter[0], len(sequence) - 1)]
    counter[0] += 1
    return value


def install_doubles():
    dashboard_module.get_cpu_percent = lambda: _next(_CPU, _cpu_index)
    def ram_sample():
        total = 16 * 1024**3
        percent = _next(_RAM, _ram_index)
        return {"used": total * percent / 100.0, "total": total, "percent": percent}

    dashboard_module.get_ram_usage = ram_sample
    dashboard_module.get_disk_usage = lambda: {
        "used": 412 * 1024**3,
        "total": 512 * 1024**3,
        "percent": _next(_DISK, _disk_index),
    }
    dashboard_module.get_battery_info = lambda: {
        "percent": _next(_BATTERY, _battery_index),
        "power_plugged": True,
    }

    applications_module.winreg = object()
    applications_module.get_installed_apps = lambda: [
        {
            "name": "Panther System Intelligence",
            "publisher": "Panther Labs",
            "version": "2.1.0",
            "install_location": "C:/Program Files/Panther",
        },
        {
            "name": "Report Viewer",
            "publisher": "Acme Software",
            "version": "4.8.2",
            "install_location": "C:/Program Files/Acme/Report Viewer",
        },
        {
            "name": "Secure Notes",
            "publisher": "Northwind",
            "version": "1.3",
            "install_location": "C:/Program Files/Northwind/Notes",
        },
    ]

    startup_module.get_startup_entries = lambda: [
        {
            "name": "Panther Agent",
            "command": "C:\\Program Files\\Panther\\agent.exe --background",
            "scope": "HKCU",
            "enabled": True,
        },
        {
            "name": "Cloud Sync",
            "command": "C:\\Program Files\\Cloud\\sync.exe --silent",
            "scope": "HKLM",
            "enabled": True,
        },
        {
            "name": "Backup Helper",
            "command": "C:\\Tools\\backup.exe /schedule",
            "scope": "HKLM",
            "enabled": True,
        },
    ]

    history_module.get_recent = lambda limit=100: [
        (42, "2026-11-05T09:41:12", "storage", "Cleared 1.8 GB of temporary files"),
        (41, "2026-11-05T09:38:04", "security", "Changed permissions on 3 files"),
        (40, "2026-11-05T09:31:55", "startup", "Reviewed startup entries"),
        (39, "2026-11-05T09:20:10", "action", "Exported a storage report"),
        (38, "2026-11-05T09:02:44", "metric", "Recorded a memory sample"),
    ]


def build_screens():
    dashboard = DashboardScreen()
    dashboard.timer.stop()
    for _ in range(6):
        dashboard.refresh()
    applications = ApplicationsScreen()
    startup = StartupScreen()
    history = HistoryScreen()
    history.timer.stop()
    history.table.selectRow(0)
    return (
        ("dashboard", dashboard),
        ("applications", applications),
        ("startup", startup),
        ("history", history),
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


def capture_state_screens(app):
    applications_module.winreg = None
    capture(app, "applications-unsupported", ApplicationsScreen())

    applications_module.winreg = object()
    applications_module.get_installed_apps = lambda: []
    capture(app, "applications-empty", ApplicationsScreen())

    def unsupported():
        raise startup_module.UnsupportedPlatformError(
            "Startup app management requires the Windows registry, which is "
            "not available on this platform."
        )

    startup_module.get_startup_entries = unsupported
    capture(app, "startup-unsupported", StartupScreen())

    startup_module.get_startup_entries = lambda: []
    capture(app, "startup-empty", StartupScreen())

    history_module.get_recent = lambda limit=100: []
    empty_history = HistoryScreen()
    empty_history.timer.stop()
    capture(app, "history-empty", empty_history)

    def dashboard_error():
        raise OSError("metrics unavailable")

    dashboard_module.get_cpu_percent = dashboard_error
    degraded = DashboardScreen()
    degraded.timer.stop()
    capture(app, "dashboard-degraded", degraded)


def main() -> int:
    install_doubles()
    os.makedirs(OUT_DIR, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    ThemeManager.apply_theme(app, "light")
    screens = build_screens()

    for theme in ("light", "dark"):
        ThemeManager.apply_theme(app, theme)
        app.processEvents()
        for name, screen in screens:
            for width, height in SIZES:
                capture(app, name, screen, width, height)
        capture_state_screens(app)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
