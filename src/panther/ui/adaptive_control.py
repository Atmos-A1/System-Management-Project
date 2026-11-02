"""Monitor-first adaptive resource intelligence screen.

All sampling and classification runs in a worker thread. Adaptive execution is
intentionally unavailable in V1; this screen is informational and auditable.
"""
from datetime import datetime, timezone

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox,
    QListWidget, QListWidgetItem, QPushButton, QMessageBox,
)

from ..services.workload_detector import WorkloadDetector
from ..services.adaptive_policy_engine import AdaptivePolicyEngine
from ..services.process_classifier import ProcessClassifier
from ..services.resource_controller import ResourceController


class AdaptiveSampleThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, detector, policy_engine, parent=None):
        super().__init__(parent)
        self.detector = detector
        self.policy_engine = policy_engine
        self.classifier = ProcessClassifier()

    def run(self):
        try:
            system_sample = self.detector.sample_system()
            if self.isInterruptionRequested():
                return
            process_samples = self.detector.sample_processes(cancel_check=self.isInterruptionRequested)
            if self.isInterruptionRequested():
                return
            workload = self.detector.classify_workload()
            recommendations = self.policy_engine.evaluate(workload, {
                "cpu_percent": system_sample.cpu_percent if system_sample else None,
                "memory_percent": system_sample.memory_percent if system_sample else None,
                "memory_available": system_sample.memory_available if system_sample else None,
                "sample_timestamp": system_sample.timestamp if system_sample else None,
            })
            applications = []
            for sample in process_samples:
                if self.isInterruptionRequested():
                    return
                classification = self.classifier.classify({
                    "pid": sample.pid, "name": sample.name, "exe": sample.exe,
                    "username": sample.username,
                })
                if classification.get("category") != "User application":
                    continue
                applications.append({
                    "pid": sample.pid, "name": sample.name,
                    "cpu": sample.cpu_percent, "memory": sample.memory_rss,
                    "category": classification.get("category"),
                })
            applications.sort(
                key=lambda item: (item["memory"] or 0, item["cpu"] or 0), reverse=True
            )
            self.completed.emit({
                "system": system_sample, "workload": workload,
                "recommendations": recommendations.recommendations,
                "applications": applications[:12],
            })
        except Exception as exc:
            self.failed.emit(str(exc))


class AdaptiveControlScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("adaptiveControlScreen")
        self.detector = WorkloadDetector()
        self.policy_engine = AdaptivePolicyEngine()
        self.resource_controller = ResourceController()
        self._worker = None
        self._selected_action_id = None
        self._build_ui()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self.refresh)

    def _metric(self, layout, label):
        card = QFrame()
        card.setObjectName("metricCard")
        box = QVBoxLayout(card)
        caption, value = QLabel(label), QLabel("—")
        caption.setObjectName("muted")
        value.setStyleSheet("font-size:20px;font-weight:700")
        box.addWidget(caption)
        box.addWidget(value)
        layout.addWidget(card)
        return value

    def _build_ui(self):
        self.setStyleSheet("""
            QWidget#adaptiveControlScreen {background:#f5f7fb;color:#172033}
            QFrame#metricCard,QFrame#panel {background:white;border:1px solid #e4e9f1;border-radius:9px}
            QLabel#title {font-size:22px;font-weight:700}
            QLabel#muted {color:#68758a}
            QComboBox,QPushButton {padding:8px;border-radius:7px}
            QListWidget {background:white;border:1px solid #e4e9f1;border-radius:8px}
            QPushButton {background:#2458c6;color:white}
            QPushButton:disabled {background:#aab5c6}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        top = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel("Adaptive Resource Intelligence")
        title.setObjectName("title")
        subtitle = QLabel("Monitor system pressure and receive evidence-based recommendations.")
        subtitle.setObjectName("muted")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        top.addLayout(heading)
        top.addStretch()
        self.mode = QComboBox()
        self.mode.addItems(["Monitor (default)", "Adaptive Recommendations", "Adaptive Control (unavailable)"])
        self.mode.setAccessibleName("Adaptive resource mode")
        model = self.mode.model()
        blocked = model.item(2)
        if blocked is not None:
            blocked.setEnabled(False)
            blocked.setToolTip("Adaptive execution is disabled in V1 pending Windows acceptance and safety validation.")
        top.addWidget(self.mode)
        layout.addLayout(top)

        metrics = QHBoxLayout()
        self.cpu_value = self._metric(metrics, "System CPU")
        self.memory_value = self._metric(metrics, "System RAM")
        self.available_value = self._metric(metrics, "Available RAM")
        self.workload_value = self._metric(metrics, "Workload")
        self.pressure_value = self._metric(metrics, "Pressure")
        layout.addLayout(metrics)

        self.status = QLabel("Waiting for the first background measurement…")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)

        panels = QHBoxLayout()
        app_panel = QFrame()
        app_panel.setObjectName("panel")
        app_layout = QVBoxLayout(app_panel)
        app_layout.addWidget(QLabel("Running user-application candidates"))
        self.app_list = QListWidget()
        app_layout.addWidget(self.app_list)
        panels.addWidget(app_panel, 1)

        right_panel = QFrame()
        right_panel.setObjectName("panel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("Adaptive recommendations"))
        self.recommendation_list = QListWidget()
        right_layout.addWidget(self.recommendation_list)
        panels.addWidget(right_panel, 1)
        layout.addLayout(panels, 1)

        history_panel = QFrame()
        history_panel.setObjectName("panel")
        history_layout = QVBoxLayout(history_panel)
        history_header = QHBoxLayout()
        history_header.addWidget(QLabel("Resource-control action history"))
        history_header.addStretch()
        self.rollback_button = QPushButton("Roll back selected action")
        self.rollback_button.setEnabled(False)
        self.rollback_button.clicked.connect(self._rollback_selected)
        history_header.addWidget(self.rollback_button)
        history_layout.addLayout(history_header)
        self.history_list = QListWidget()
        self.history_list.currentItemChanged.connect(self._history_selection_changed)
        history_layout.addWidget(self.history_list)
        layout.addWidget(history_panel)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self._refresh_history()
        self._mode_changed(0)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_timer.start()
        self.refresh()

    def hideEvent(self, event):
        self._refresh_timer.stop()
        super().hideEvent(event)

    def refresh(self):
        if self._worker is not None and self._worker.isRunning():
            return
        self.status.setText("Collecting system and application measurements in the background…")
        worker = AdaptiveSampleThread(self.detector, self.policy_engine, self)
        worker.completed.connect(self._on_sample_ready)
        worker.failed.connect(self._on_sample_failed)
        worker.finished.connect(lambda: self._worker_finished(worker))
        self._worker = worker
        worker.start()

    def _worker_finished(self, worker):
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

    def _on_sample_ready(self, snapshot):
        system, workload = snapshot["system"], snapshot["workload"]
        if system is not None:
            self.cpu_value.setText("—" if system.cpu_percent is None else "{:.1f}%".format(system.cpu_percent))
            self.memory_value.setText("—" if system.memory_percent is None else "{:.1f}%".format(system.memory_percent))
            available = system.memory_available
            self.available_value.setText("—" if available is None else "{:.0f} MiB".format(available / (1024 * 1024)))
        self.workload_value.setText(workload.classification.replace("_", " ").title())
        self.pressure_value.setText(workload.pressure.title())
        self.app_list.clear()
        for app in snapshot["applications"]:
            cpu = "CPU —" if app["cpu"] is None else "CPU {:.1f}%".format(app["cpu"])
            memory = "RAM —" if app["memory"] is None else "RAM {:.0f} MiB".format(app["memory"] / (1024 * 1024))
            self.app_list.addItem("{} · PID {} · {} · {}".format(app["name"], app["pid"], cpu, memory))
        if not snapshot["applications"]:
            self.app_list.addItem("No verified user-application candidates in this sample.")
        self._recommendations = snapshot["recommendations"]
        self._render_recommendations()
        self.status.setText(
            "Updated {} · {} workload samples · confidence {:.0f}%".format(
                datetime.now().strftime("%H:%M:%S"), workload.samples_count, workload.confidence * 100
            )
        )

    def _on_sample_failed(self, message):
        self.status.setText("Measurement unavailable: {}".format(message))

    def _mode_changed(self, index):
        if index == 0:
            self.recommendation_list.clear()
            self.recommendation_list.addItem("Monitor mode is active. Measurements are shown without suggested changes.")
        else:
            self._render_recommendations()

    def _render_recommendations(self):
        self.recommendation_list.clear()
        if self.mode.currentIndex() == 0:
            self.recommendation_list.addItem("Switch to Adaptive Recommendations to review evidence-based guidance.")
            return
        recommendations = getattr(self, "_recommendations", [])
        if not recommendations:
            self.recommendation_list.addItem("No recommendation: measurements are insufficient, stale, or pressure is not sustained.")
            return
        for recommendation in recommendations:
            self.recommendation_list.addItem(
                "{}\n{}\nEvidence: {}".format(
                    recommendation.reason, recommendation.explanation,
                    "; ".join(recommendation.evidence),
                )
            )

    def _refresh_history(self):
        self.history_list.clear()
        for action in self.resource_controller.get_history():
            item = QListWidgetItem(
                "{} · PID {} · {} · {}".format(
                    action.action_type, action.target_pid or "—", action.result,
                    action.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                )
            )
            item.setData(Qt.UserRole, action.id)
            self.history_list.addItem(item)
        if self.history_list.count() == 0:
            self.history_list.addItem("No resource-control actions have been recorded.")
        self.rollback_button.setEnabled(False)

    def _history_selection_changed(self, current, previous):
        self._selected_action_id = current.data(Qt.UserRole) if current else None
        action = next((a for a in self.resource_controller.get_history()
                       if a.id == self._selected_action_id), None)
        self.rollback_button.setEnabled(bool(action and action.reversible and action.result == "success"))

    def _rollback_selected(self):
        if not self._selected_action_id:
            return
        answer = QMessageBox.question(
            self, "Confirm rollback",
            "Restore the previously recorded priority for this exact process instance? Panther will re-check its identity first.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        ok, message = self.resource_controller.rollback(self._selected_action_id, user_confirmed=True)
        QMessageBox.information(self, "Rollback result", message)
        self._refresh_history()

    def closeEvent(self, event):
        self._refresh_timer.stop()
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait()
        super().closeEvent(event)
