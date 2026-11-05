"""Monitor-first adaptive resource intelligence screen.

All sampling and classification runs in a worker thread. Adaptive execution is
intentionally unavailable in V1; this screen is informational and auditable.
"""
from datetime import datetime

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..services.workload_detector import WorkloadDetector
from ..services.adaptive_policy_engine import AdaptivePolicyEngine
from ..services.process_classifier import ProcessClassifier
from ..services.resource_controller import ResourceController
from .components import (
    MetricCard, PageScaffold, SectionCard, StatusBanner, Toolbar,
)


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
        self._recommendations = []
        self._build_ui()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self.refresh)

    def _metric(self, layout, title, detail, accessible_name):
        card = MetricCard(
            title, "—", detail, progress_visible=False, compact=True
        )
        card.title_label.setAccessibleName(f"{title} metric")
        card.value_label.setAccessibleName(accessible_name)
        layout.addWidget(card)
        return card

    def _list(self, accessible_name):
        widget = QListWidget()
        widget.setObjectName("detailList")
        widget.setAccessibleName(accessible_name)
        widget.setSelectionMode(QListWidget.SingleSelection)
        widget.setWordWrap(True)
        widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return widget

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scaffold = PageScaffold(
            "Adaptive Resource Intelligence",
            "Monitor system pressure and receive evidence-based recommendations.",
            margins=20,
            spacing=14,
        )
        outer.addWidget(self.scaffold)

        mode_bar = Toolbar()
        mode_label = QLabel("Operating mode")
        mode_label.setObjectName("pageSubtitle")
        self.mode = QComboBox()
        self.mode.addItems([
            "Monitor (default)",
            "Adaptive Recommendations",
            "Adaptive Control (unavailable)",
        ])
        self.mode.setAccessibleName("Adaptive resource mode")
        model = self.mode.model()
        blocked = model.item(2)
        if blocked is not None:
            blocked.setEnabled(False)
            blocked.setToolTip(
                "Adaptive execution is disabled in V1 pending Windows acceptance "
                "and safety validation."
            )
        mode_bar.add_widget(mode_label)
        mode_bar.add_widget(self.mode)
        mode_bar.add_stretch()
        self.scaffold.add_widget(mode_bar)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.cpu_card = self._metric(
            metrics, "System CPU", "Current measured load", "Measured system CPU usage"
        )
        self.memory_card = self._metric(
            metrics, "System RAM", "Current measured usage", "Measured system memory usage"
        )
        self.available_card = self._metric(
            metrics, "Available RAM", "Measured free memory", "Measured available memory"
        )
        self.workload_card = self._metric(
            metrics, "Workload", "Evidence-based classification", "Classified workload"
        )
        self.pressure_card = self._metric(
            metrics, "Pressure", "Sustained pressure indicator", "Classified pressure"
        )
        self.cpu_value = self.cpu_card.value_label
        self.memory_value = self.memory_card.value_label
        self.available_value = self.available_card.value_label
        self.workload_value = self.workload_card.value_label
        self.pressure_value = self.pressure_card.value_label
        self.scaffold.add_layout(metrics)

        self.status_banner = StatusBanner(
            "Waiting for the first background measurement…", "loading"
        )
        self.status = self.status_banner.message_label
        self.status_label = self.status
        self.scaffold.add_widget(self.status_banner)

        panels = QHBoxLayout()
        panels.setSpacing(12)
        self.applications_card = SectionCard(
            "Running user-application candidates",
            "Top measured consumers in the latest sample.",
        )
        self.app_list = self._list("Running user-application candidates")
        self.applications_card.add_widget(self.app_list)
        panels.addWidget(self.applications_card, 1)

        self.recommendations_card = SectionCard(
            "Adaptive recommendations",
            "Guidance only. Panther never closes or changes a process from this view.",
        )
        self.recommendation_list = self._list("Adaptive recommendations")
        self.recommendations_card.add_widget(self.recommendation_list)
        panels.addWidget(self.recommendations_card, 1)

        self.history_card = SectionCard(
            "Resource-control action history",
            "Rollback requires confirmation and re-verifies the process identity.",
        )
        history_actions = QHBoxLayout()
        history_actions.addStretch()
        self.rollback_button = QPushButton("Roll back selected action")
        self.rollback_button.setProperty("variant", "secondary")
        self.rollback_button.setProperty("secondary", True)
        self.rollback_button.setAccessibleName("Roll back selected action")
        self.rollback_button.setEnabled(False)
        self.rollback_button.clicked.connect(self._rollback_selected)
        history_actions.addWidget(self.rollback_button)
        self.history_card.add_layout(history_actions)
        self.history_list = self._list("Resource-control action history")
        self.history_list.currentItemChanged.connect(self._history_selection_changed)
        self.history_card.add_widget(self.history_list)

        lower = QWidget()
        lower.setMinimumSize(0, 0)
        lower_layout = QVBoxLayout(lower)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_layout.setSpacing(14)
        lower_layout.addLayout(panels, 1)
        lower_layout.addWidget(self.history_card, 1)

        self.lower_scroll = QScrollArea()
        self.lower_scroll.setWidgetResizable(True)
        self.lower_scroll.setMinimumSize(0, 0)
        self.lower_scroll.setAccessibleName("Adaptive resource details")
        self.lower_scroll.setWidget(lower)
        self.scaffold.add_widget(self.lower_scroll, 1)

        self.mode.currentIndexChanged.connect(self._mode_changed)
        self._refresh_history()
        self._mode_changed(0)

    # -- lifecycle --------------------------------------------------------

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
        self.status_banner.set_state(
            "loading",
            "Collecting system and application measurements in the background…",
        )
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

    # -- rendering --------------------------------------------------------

    def _on_sample_ready(self, snapshot):
        system, workload = snapshot["system"], snapshot["workload"]
        if system is not None:
            cpu = system.cpu_percent
            memory = system.memory_percent
            available = system.memory_available
            self.cpu_value.setText("—" if cpu is None else "{:.1f}%".format(cpu))
            self.memory_value.setText("—" if memory is None else "{:.1f}%".format(memory))
            self.available_value.setText(
                "—" if available is None else "{:.0f} MiB".format(available / (1024 * 1024))
            )
        self.workload_value.setText(workload.classification.replace("_", " ").title())
        self.pressure_value.setText(workload.pressure.title())
        self.pressure_card.set_detail(
            "Sustained pressure detected" if workload.pressure == "high"
            else "No sustained pressure"
        )
        self.app_list.clear()
        for app in snapshot["applications"]:
            cpu = "CPU —" if app["cpu"] is None else "CPU {:.1f}%".format(app["cpu"])
            memory = "RAM —" if app["memory"] is None else "RAM {:.0f} MiB".format(app["memory"] / (1024 * 1024))
            self.app_list.addItem("{} · PID {} · {} · {}".format(app["name"], app["pid"], cpu, memory))
        if not snapshot["applications"]:
            self.app_list.addItem("No verified user-application candidates in this sample.")
        self._recommendations = snapshot["recommendations"]
        self._render_recommendations()
        self.status_banner.set_state(
            "success",
            "Updated {} · {} workload samples · confidence {:.0f}%".format(
                datetime.now().strftime("%H:%M:%S"),
                workload.samples_count,
                workload.confidence * 100,
            ),
        )

    def _on_sample_failed(self, message):
        self.status_banner.set_state(
            "error", "Measurement unavailable: {}".format(message)
        )

    def _mode_changed(self, index):
        if index == 0:
            self.recommendation_list.clear()
            self.recommendation_list.addItem(
                "Monitor mode is active. Measurements are shown without suggested changes."
            )
        else:
            self._render_recommendations()

    def _render_recommendations(self):
        self.recommendation_list.clear()
        if self.mode.currentIndex() == 0:
            self.recommendation_list.addItem(
                "Monitor mode is active. Measurements are shown without suggested changes."
            )
            return
        recommendations = getattr(self, "_recommendations", [])
        if not recommendations:
            self.recommendation_list.addItem(
                "No recommendation: measurements are insufficient, stale, or "
                "pressure is not sustained."
            )
            return
        for recommendation in recommendations:
            self.recommendation_list.addItem(
                "{}\n{}\nEvidence: {}".format(
                    recommendation.reason, recommendation.explanation,
                    "; ".join(recommendation.evidence),
                )
            )

    # -- resource-control history ----------------------------------------

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
        self.rollback_button.setEnabled(
            bool(action and action.reversible and action.result == "success")
        )

    def _rollback_selected(self):
        if not self._selected_action_id:
            return
        answer = QMessageBox.question(
            self, "Confirm rollback",
            "Restore the previously recorded priority for this exact process "
            "instance? Panther will re-check its identity first.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        ok, message = self.resource_controller.rollback(
            self._selected_action_id, user_confirmed=True
        )
        QMessageBox.information(self, "Rollback result", message)
        self._refresh_history()

    def closeEvent(self, event):
        self._refresh_timer.stop()
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait()
        super().closeEvent(event)
