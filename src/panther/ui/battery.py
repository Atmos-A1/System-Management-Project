"""Battery screen - power status and insights.

Shows battery information with clear distinction between measured and estimated values.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QGridLayout, QProgressBar, QPushButton, QMessageBox
)
from PySide6.QtCore import QTimer, Qt

from ..config import config
from ..services.battery_adapter import get_battery_status


class BatteryScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("batteryScreen")
        self._top_procs = []
        self.setStyleSheet("""
            QWidget {
                background-color: #f7f9fc;
            }
            QFrame#card {
                background-color: #ffffff;
                border-radius: 12px;
                border: 1px solid #e5e7eb;
            }
            QLabel#cardTitle {
                font-size: 13px;
                font-weight: 600;
                color: #1f2937;
            }
            QLabel#cardValue {
                font-size: 32px;
                font-weight: 700;
                color: #2563eb;
            }
            QLabel#cardDetail {
                font-size: 11px;
                color: #6b7280;
            }
            QLabel#headerTitle {
                font-size: 24px;
                font-weight: 700;
                color: #111827;
            }
            QLabel#headerSubtitle {
                font-size: 12px;
                color: #6b7280;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)
        layout.setAlignment(Qt.AlignTop)

        header = QWidget()
        header.setStyleSheet("background: transparent;")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        
        title = QLabel("Battery & Power")
        title.setObjectName("headerTitle")
        subtitle = QLabel("Battery status and power information (measured vs estimated)")
        subtitle.setObjectName("headerSubtitle")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(16)
        
        self.charge_card = self.create_card("Charge Level", "N/A")
        self.status_card = self.create_card("Status", "N/A")
        self.runtime_card = self.create_card("Estimated Runtime", "N/A")
        
        grid.addWidget(self.charge_card, 0, 0)
        grid.addWidget(self.status_card, 0, 1)
        grid.addWidget(self.runtime_card, 1, 0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        self.grid = grid
        
        # Detailed info section
        details_frame = QFrame()
        details_frame.setObjectName("card")
        details_layout = QVBoxLayout(details_frame)
        details_layout.setContentsMargins(22, 16, 22, 16)
        details_layout.setSpacing(8)
        details_title = QLabel("Power Details & Drain")
        details_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #111827;")
        details_layout.addWidget(details_title)
        self.battery_details = QLabel("Collecting battery information...")
        self.battery_details.setWordWrap(True)
        self.battery_details.setStyleSheet("color: #374151; font-size: 12px;")
        details_layout.addWidget(self.battery_details)
        # Kill buttons
        self.kill_buttons_layout = QVBoxLayout()
        self.kill_buttons_layout.setSpacing(4)
        details_layout.addLayout(self.kill_buttons_layout)
        layout.addWidget(details_frame)
        
        note = QLabel("Note: Windows does not always provide accurate per-process wattage. Values shown are from available system interfaces and psutil sensors_battery.")
        note.setStyleSheet("color: #6b7280; font-size: 11px;")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()

        self.timer = QTimer(self)
        self.timer.setInterval(config.refresh_interval_seconds * 1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def create_card(self, title, value):
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumHeight(170)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 18, 22, 18)
        card_layout.setSpacing(10)
        
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        
        value_label = QLabel(value)
        value_label.setObjectName("cardValue")
        value_label.setAlignment(Qt.AlignCenter)
        
        detail_label = QLabel("")
        detail_label.setObjectName("cardDetail")
        detail_label.setAlignment(Qt.AlignCenter)
        detail_label.setWordWrap(True)
        
        progress = QProgressBar()
        progress.setTextVisible(False)
        progress.setFixedHeight(8)
        progress.setStyleSheet("""
            QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
            QProgressBar::chunk { background-color: #2563eb; border-radius: 4px; }
        """)
        
        card_layout.addWidget(title_label)
        card_layout.addSpacing(6)
        card_layout.addWidget(value_label)
        card_layout.addWidget(detail_label)
        card_layout.addSpacing(10)
        card_layout.addWidget(progress)
        
        card.value_label = value_label
        card.detail_label = detail_label
        card.progress = progress
        return card
    
    def _update_kill_buttons(self):
        # Clear existing
        while self.kill_buttons_layout.count():
            item = self.kill_buttons_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self._top_procs:
            return
        from ..services.process_classifier import classify_process
        from ..services.process_actions import process_action_manager
        for p in self._top_procs[:4]:
            try:
                classification = classify_process(p)
                if not classification.get('can_terminate'):
                    continue
            except Exception:
                continue
            btn = QPushButton(f"Kill {p.get('name')} (PID {p.get('pid')})")
            btn.setStyleSheet("padding: 6px 10px; border-radius: 6px; background-color: #dc2626; color: #ffffff; border: none; text-align: left;")
            pid = p.get('pid')
            proc = p
            btn.clicked.connect(lambda checked, pid=pid, proc=proc: self._kill_consumer(pid, proc))
            self.kill_buttons_layout.addWidget(btn)
    
    def _kill_consumer(self, pid, proc):
        try:
            from ..services.process_classifier import classify_process
            from ..services.process_actions import process_action_manager
            classification = classify_process(proc)
        except Exception:
            classification = {"category": "Unknown", "risk_level": "Unknown", "explanation": ""}
        reply = QMessageBox.warning(
            self, "Confirm Kill",
            f"Kill {proc.get('name')} (PID {pid})?\n\nCategory: {classification.get('category')}\nRisk: {classification.get('risk_level')}\n\n{classification.get('explanation')}\n\nThis may cause data loss.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                result = process_action_manager.graceful_close(pid)
                if result.get('success'):
                    QMessageBox.information(self, "Success", result.get('message', 'Process closed'))
                    self.refresh()
                elif result.get('needs_force'):
                    reply2 = QMessageBox.question(self, "Not Responding", "Try force kill?", QMessageBox.Yes | QMessageBox.No)
                    if reply2 == QMessageBox.Yes:
                        res2 = process_action_manager.force_kill(pid)
                        if res2.get('success'):
                            QMessageBox.information(self, "Success", res2.get('message', 'Process killed'))
                            self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def refresh(self):
        try:
            from ..services.process_adapter import get_processes
        except Exception:
            get_processes = None
        batt = get_battery_status()
        if not batt:
            self.charge_card.value_label.setText("N/A")
            self.charge_card.detail_label.setText("No battery detected")
            self.charge_card.progress.setValue(0)
            self.charge_card.progress.setStyleSheet("""
                QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                QProgressBar::chunk { background-color: #9ca3af; border-radius: 4px; }
            """)
            self.status_card.value_label.setText("N/A")
            self.status_card.detail_label.setText("Not available")
            self.status_card.progress.setValue(0)
            self.status_card.progress.setStyleSheet("""
                QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                QProgressBar::chunk { background-color: #9ca3af; border-radius: 4px; }
            """)
            self.runtime_card.value_label.setText("N/A")
            self.runtime_card.detail_label.setText("Not available")
            self.runtime_card.progress.setValue(0)
            self.runtime_card.progress.setStyleSheet("""
                QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                QProgressBar::chunk { background-color: #9ca3af; border-radius: 4px; }
            """)
            if hasattr(self, 'battery_details'):
                self.battery_details.setText("No battery detected on this system. Runtime estimation unavailable.")
            return
        
        percent = batt.get("percent", 0) or 0
        self.charge_card.value_label.setText(f"{percent:.0f}%")
        self.charge_card.detail_label.setText("Measured charge level")
        self.charge_card.progress.setValue(int(max(0, min(100, percent))))
        if percent < 20:
            self.charge_card.progress.setStyleSheet("""
                QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                QProgressBar::chunk { background-color: #dc2626; border-radius: 4px; }
            """)
        elif percent < 40:
            self.charge_card.progress.setStyleSheet("""
                QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                QProgressBar::chunk { background-color: #f59e0b; border-radius: 4px; }
            """)
        else:
            self.charge_card.progress.setStyleSheet("""
                QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                QProgressBar::chunk { background-color: #22c55e; border-radius: 4px; }
            """)
        
        charging = batt.get("power_plugged")
        if charging:
            self.status_card.value_label.setText("Charging")
            self.status_card.detail_label.setText("AC power connected (measured)")
            self.status_card.progress.setStyleSheet("""
                QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                QProgressBar::chunk { background-color: #22c55e; border-radius: 4px; }
            """)
            self.status_card.progress.setValue(100)
        else:
            self.status_card.value_label.setText("Discharging")
            self.status_card.detail_label.setText("On battery (measured)")
            self.status_card.progress.setStyleSheet("""
                QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                QProgressBar::chunk { background-color: #f59e0b; border-radius: 4px; }
            """)
            self.status_card.progress.setValue(100)
        
        secs = batt.get("secsleft")
        try:
            secs_int = int(secs) if secs is not None else None
        except Exception:
            secs_int = None
        # Handle Windows weird values (common: 0xFFFFFFFF = 4294967295)
        if secs_int is None or secs_int <= 0 or secs_int >= 2**31 or secs_int > 86400*365:
            if charging:
                self.runtime_card.value_label.setText("Plugged in")
                self.runtime_card.detail_label.setText("Charging from AC power")
                self.runtime_card.progress.setValue(100)
                self.runtime_card.progress.setStyleSheet("""
                    QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #22c55e; border-radius: 4px; }
                """)
            else:
                # Estimate based on discharge rate if possible - use reasonable estimate
                # Many laptops don't report remaining time accurately
                if percent > 0:
                    # Rough estimate: ~2-4 hours typical, scale by percentage
                    est_hours = max(0.5, (percent / 100.0) * 3.5)
                    hrs_est = int(est_hours)
                    mins_est = int((est_hours - hrs_est) * 60)
                    if hrs_est == 0:
                        self.runtime_card.value_label.setText(f"~{mins_est} min left")
                    elif mins_est == 0:
                        self.runtime_card.value_label.setText(f"~{hrs_est} hr left")
                    else:
                        self.runtime_card.value_label.setText(f"~{hrs_est} hr {mins_est} min left")
                    self.runtime_card.detail_label.setText("Estimated (based on charge level)")
                else:
                    self.runtime_card.value_label.setText("Unknown")
                    self.runtime_card.detail_label.setText("Time estimate unavailable")
                self.runtime_card.progress.setValue(min(100, max(10, int(percent))))
                self.runtime_card.progress.setStyleSheet("""
                    QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #2563eb; border-radius: 4px; }
                """)
        elif secs_int > 0 and secs_int < 86400*7:  # reasonable value
            hrs, rem = divmod(secs_int, 3600)
            mins = rem // 60
            if hrs == 0:
                self.runtime_card.value_label.setText(f"{mins} min left")
            elif mins == 0:
                self.runtime_card.value_label.setText(f"{hrs} hr left")
            else:
                self.runtime_card.value_label.setText(f"{hrs} hr {mins} min left")
            self.runtime_card.detail_label.setText("Estimated time remaining (system)")
            self.runtime_card.progress.setValue(min(100, max(5, int((percent / 100.0) * 100))))
            self.runtime_card.progress.setStyleSheet("""
                QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                QProgressBar::chunk { background-color: #2563eb; border-radius: 4px; }
            """)
        else:
            self.runtime_card.value_label.setText("N/A")
            self.runtime_card.detail_label.setText("Not available")
            self.runtime_card.progress.setValue(0)
            self.runtime_card.progress.setStyleSheet("""
                QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                QProgressBar::chunk { background-color: #9ca3af; border-radius: 4px; }
            """)
        
        # Build drain hierarchy
        drain_lines = []
        drain_lines.append(f"<b>Charge:</b> {percent:.0f}% | <b>State:</b> {'Charging' if charging else 'Discharging'}")
        if secs_int and secs_int > 0 and secs_int < 86400*7 and not charging:
            hrs, rem = divmod(secs_int, 3600)
            mins = rem // 60
            if hrs == 0:
                drain_lines.append(f"<b>Estimated runtime:</b> {mins} min left (Windows system estimate)")
            elif mins == 0:
                drain_lines.append(f"<b>Estimated runtime:</b> {hrs} hr left (Windows system estimate)")
            else:
                drain_lines.append(f"<b>Estimated runtime:</b> {hrs} hr {mins} min left (Windows system estimate)")
        elif charging and secs_int and secs_int > 0 and secs_int < 86400*7:
            hrs, rem = divmod(secs_int, 3600)
            mins = rem // 60
            if hrs == 0:
                drain_lines.append(f"<b>Time to full (est):</b> {mins} min")
            elif mins == 0:
                drain_lines.append(f"<b>Time to full (est):</b> {hrs} hr")
            else:
                drain_lines.append(f"<b>Time to full (est):</b> {hrs} hr {mins} min")
        # Top consumers
        self._top_procs = []
        if get_processes and not charging:
            try:
                procs = get_processes()
                # Filter out very small system noise and get meaningful consumers
                filtered = []
                for p in procs:
                    name = (p.get('name') or '').lower()
                    if name in ('system idle process', 'system', 'registry', 'smss.exe', 'csrss.exe', 'wininit.exe', 'services.exe', 'lsass.exe', 'winlogon.exe'):
                        continue
                    filtered.append(p)
                top = sorted(filtered, key=lambda x: ((x.get('memory_rss',0) or 0), (x.get('cpu_percent',0) or 0)), reverse=True)[:6]
                self._top_procs = top
                drain_lines.append("<br/><b>What's draining (hierarchical):</b>")
                for i, p in enumerate(top, 1):
                    name = p.get('name','')
                    mem_mb = (p.get('memory_rss',0) or 0) // (1024**2)
                    cpu = p.get('cpu_percent',0) or 0
                    pid = p.get('pid')
                    drain_lines.append(f"  {i}. {name} (PID {pid}) — {mem_mb} MB RAM, {cpu:.1f}% CPU")
                drain_lines.append("<br/><i>Click below to kill a consumer safely (with confirmation). System processes are excluded.</i>")
            except Exception:
                pass
        elif not charging:
            drain_lines.append("<br/><i>Per-process power breakdown not directly available; showing top memory/cpu consumers as proxies.</i>")
        else:
            drain_lines.append("<br/><i>Plugged in — battery drain not applicable.</i>")
        
        if hasattr(self, 'battery_details'):
            self.battery_details.setText("<br/>".join(drain_lines))
        # Update kill buttons
        self._update_kill_buttons()
