"""Battery screen - power status and insights.

Shows battery information with a clear distinction between measured and
estimated values. Unavailable measurements are reported as unavailable rather
than replaced with invented estimates.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMessageBox, QScrollArea, QStackedWidget,
    QVBoxLayout, QWidget,
)

from ..config import config
from ..services.battery_adapter import get_battery_status
from ..services.process_actions import process_action_manager
from ..services.process_adapter import get_processes
from ..services.process_classifier import classify_process
from .components import (
    DestructiveButton, EmptyState, KeyValueList, MetricCard, PageScaffold,
    SectionCard,
)

SYSTEM_PROCESS_NAMES = {
    "system idle process", "system", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "winlogon.exe",
}


class BatteryScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("batteryScreen")
        self._top_procs = []
        self.kill_buttons = []
        self._build_ui()

        self.timer = QTimer(self)
        self.timer.setInterval(config.refresh_interval_seconds * 1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scaffold = PageScaffold(
            "Battery & Power",
            "Battery status and power information, with measured and estimated "
            "values shown separately.",
            margins=20,
            spacing=14,
        )
        outer.addWidget(self.scaffold)

        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.charge_card = self._card(
            cards, "Charge Level", "Measured battery charge",
            "Measured battery charge level",
        )
        self.status_card = self._card(
            cards, "Status", "Measured power state",
            "Measured battery power state",
        )
        self.runtime_card = self._card(
            cards, "Estimated Runtime", "Measured or system-estimated runtime",
            "Estimated remaining battery runtime",
        )
        content_layout.addLayout(cards)

        self.details_card = SectionCard(
            "Power details",
            "Charge and power-state values are measured. Runtime is labelled "
            "by source and is never invented.",
        )
        self.details = KeyValueList()
        for key in ("Reported charge", "Power state", "Runtime source", "Battery"):
            self.details.add_row(key, "—")
        self.battery_details = QLabel(
            "Collecting battery information…"
        )
        self.battery_details.setObjectName("pageSubtitle")
        self.battery_details.setWordWrap(True)
        self.battery_details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.details_card.add_widget(self.details)
        self.details_card.add_widget(self.battery_details)
        content_layout.addWidget(self.details_card)

        self.consumers_card = SectionCard(
            "Top resource consumers",
            "Proxy indicators only: Windows does not reliably expose measured "
            "per-process wattage. System processes are excluded.",
        )
        self.consumers_note = QLabel(
            "Per-process power breakdown is not directly available. The list "
            "below shows measured memory and CPU consumers as proxies."
        )
        self.consumers_note.setObjectName("pageSubtitle")
        self.consumers_note.setWordWrap(True)
        self.consumers_card.add_widget(self.consumers_note)
        self.kill_buttons_layout = QVBoxLayout()
        self.kill_buttons_layout.setSpacing(6)
        self.consumers_card.add_layout(self.kill_buttons_layout)
        content_layout.addWidget(self.consumers_card)

        note = QLabel(
            "Note: Windows does not always provide accurate per-process "
            "wattage. Values shown come from available system interfaces and "
            "psutil sensors_battery."
        )
        note.setObjectName("pageSubtitle")
        note.setWordWrap(True)
        content_layout.addWidget(note)
        content_layout.addStretch()

        self.unsupported_state = EmptyState(
            "No battery detected",
            "Battery information is not available on this system. Panther does "
            "not fabricate charge, runtime or drain values.",
            variant="unsupported",
        )

        self.state_stack = QStackedWidget()
        self.state_stack.setObjectName("batteryStateStack")
        self.state_stack.addWidget(self.content)
        self.state_stack.addWidget(self.unsupported_state)
        self.scaffold.content_layout.addWidget(self.state_stack, 1)

    def _card(self, layout, title, detail, accessible_name):
        card = MetricCard(title, "N/A", detail, progress_visible=False)
        card.title_label.setAccessibleName(f"{title} metric")
        card.value_label.setAccessibleName(accessible_name)
        layout.addWidget(card)
        return card

    # -- refresh ----------------------------------------------------------

    def refresh(self):
        batt = get_battery_status()
        if not batt:
            self._top_procs = []
            self._clear_kill_buttons()
            self.state_stack.setCurrentWidget(self.unsupported_state)
            return

        self.state_stack.setCurrentWidget(self.content)
        percent = batt.get("percent")
        charging = bool(batt.get("power_plugged"))
        self._update_charge(percent)
        self._update_status(charging)
        self._update_runtime(batt.get("secsleft"), percent, charging)

        self.details.set_value(
            "Reported charge",
            "Unavailable" if percent is None else "{:.0f}% (measured)".format(percent),
        )
        self.details.set_value(
            "Power state",
            "Charging (measured)" if charging else "Discharging (measured)",
        )
        self.details.set_value("Battery", "Present")

        self._top_procs = []
        self._clear_kill_buttons()
        if charging:
            self.consumers_note.setText(
                "Plugged in — battery drain is not applicable while charging."
            )
            self.battery_details.setText(
                "Charge: {:.0f}% · State: Charging · Battery drain is not "
                "applicable while plugged in.".format(percent or 0)
            )
            return

        self._refresh_consumers(percent)

    def _update_charge(self, percent):
        if percent is None:
            self.charge_card.set_value("Unavailable")
            self.charge_card.set_detail("Charge measurement unavailable")
            self.charge_card.set_progress(0, "normal")
            return
        value = max(0, min(100, int(percent)))
        self.charge_card.set_value("{:.0f}%".format(percent))
        self.charge_card.set_detail("Measured charge level")
        level = "critical" if value < 20 else "warning" if value < 40 else "normal"
        self.charge_card.set_progress(value, level)
        self.charge_card.set_progress_visible(True)

    def _update_status(self, charging):
        if charging:
            self.status_card.set_value("Charging")
            self.status_card.set_detail("AC power connected (measured)")
            self.status_card.set_progress(100, "accent")
        else:
            self.status_card.set_value("Discharging")
            self.status_card.set_detail("On battery (measured)")
            self.status_card.set_progress(100, "normal")
        self.status_card.set_progress_visible(True)

    def _update_runtime(self, secsleft, percent, charging):
        try:
            secs = int(secsleft) if secsleft is not None else None
        except (TypeError, ValueError, OverflowError):
            secs = None
        # Windows sometimes reports 0xFFFFFFFF or other sentinel values.
        valid = secs is not None and 0 < secs < 86400 * 7

        if charging:
            self.runtime_card.set_value("Plugged in")
            self.runtime_card.set_detail("Charging from AC power")
            self.runtime_card.set_progress(100, "accent")
            self.runtime_card.set_progress_visible(True)
            self.details.set_value("Runtime source", "Not applicable while charging")
            return

        if valid:
            hours, remainder = divmod(secs, 3600)
            minutes = remainder // 60
            if hours == 0:
                value = "{} min left".format(minutes)
            elif minutes == 0:
                value = "{} hr left".format(hours)
            else:
                value = "{} hr {} min left".format(hours, minutes)
            self.runtime_card.set_value(value)
            self.runtime_card.set_detail("Estimated time remaining (system)")
            if percent is not None:
                self.runtime_card.set_progress(
                    max(0, min(100, int(percent))), "normal"
                )
            self.runtime_card.set_progress_visible(True)
            self.details.set_value("Runtime source", "System estimate")
            return

        # No invented estimate: the system did not provide a usable value.
        self.runtime_card.set_value("Unknown")
        self.runtime_card.set_detail("Time estimate unavailable")
        self.runtime_card.set_progress_visible(False)
        self.details.set_value("Runtime source", "Unavailable")

    def _refresh_consumers(self, percent):
        try:
            procs = get_processes()
        except Exception as exc:
            self.consumers_note.setText(
                "Top consumers are unavailable: {}".format(exc)
            )
            self.battery_details.setText(
                "Charge: {:.0f}% · State: Discharging · Consumer list unavailable."
                .format(percent or 0)
            )
            return

        filtered = []
        for process in procs:
            name = (process.get("name") or "").lower()
            if name in SYSTEM_PROCESS_NAMES:
                continue
            filtered.append(process)
        top = sorted(
            filtered,
            key=lambda item: (
                (item.get("memory_rss", 0) or 0),
                (item.get("cpu_percent", 0) or 0),
            ),
            reverse=True,
        )[:6]
        self._top_procs = top
        self._update_kill_buttons()
        self.consumers_note.setText(
            "Per-process power breakdown is not directly available. The list "
            "below shows measured memory and CPU consumers as proxies."
        )
        lines = [
            "Charge: {:.0f}% · State: Discharging".format(percent or 0),
            "What's draining (proxy hierarchy):",
        ]
        for index, process in enumerate(top, 1):
            memory = (process.get("memory_rss", 0) or 0) // (1024 ** 2)
            cpu = process.get("cpu_percent", 0) or 0
            lines.append(
                "  {}. {} (PID {}) — {} MB RAM, {:.1f}% CPU".format(
                    index, process.get("name", ""), process.get("pid"),
                    memory, cpu,
                )
            )
        if not top:
            lines.append("No notable resource consumers were measured.")
        self.battery_details.setText("\n".join(lines))

    # -- process actions --------------------------------------------------

    def _clear_kill_buttons(self):
        while self.kill_buttons_layout.count():
            item = self.kill_buttons_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.kill_buttons = []

    def _update_kill_buttons(self):
        self._clear_kill_buttons()
        if not self._top_procs:
            return
        for process in self._top_procs[:4]:
            try:
                classification = classify_process(process)
                if not classification.get("can_terminate"):
                    continue
            except Exception:
                continue
            name = process.get("name")
            pid = process.get("pid")
            button = DestructiveButton("Kill {} (PID {})".format(name, pid))
            button.setAccessibleName("Kill {} process {}".format(name, pid))
            button.setToolTip(
                "Closing this process requires confirmation and may cause data loss."
            )
            button.clicked.connect(
                lambda checked=False, pid=pid, proc=process: self._kill_consumer(pid, proc)
            )
            self.kill_buttons_layout.addWidget(button)
            self.kill_buttons.append(button)

    def _kill_consumer(self, pid, proc):
        try:
            classification = classify_process(proc)
        except Exception:
            classification = {
                "category": "Unknown", "risk_level": "Unknown", "explanation": ""
            }
        reply = QMessageBox.warning(
            self, "Confirm Kill",
            "Kill {} (PID {})?\n\nCategory: {}\nRisk: {}\n\n{}\n\n"
            "This may cause data loss.".format(
                proc.get("name"), pid, classification.get("category"),
                classification.get("risk_level"), classification.get("explanation"),
            ),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            result = process_action_manager.graceful_close(pid)
            if result.get("success"):
                QMessageBox.information(
                    self, "Success", result.get("message", "Process closed")
                )
                self.refresh()
            elif result.get("needs_force"):
                reply2 = QMessageBox.question(
                    self, "Not Responding", "Try force kill?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply2 == QMessageBox.Yes:
                    res2 = process_action_manager.force_kill(pid)
                    if res2.get("success"):
                        QMessageBox.information(
                            self, "Success", res2.get("message", "Process killed")
                        )
                        self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
