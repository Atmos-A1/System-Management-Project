"""Responsive Process Explorer with background discovery and identity-aware selection."""
from datetime import datetime
from typing import Callable

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QThread,
    QTimer, Qt, Signal,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QScrollArea, QSplitter, QTableView, QVBoxLayout,
    QWidget,
)

from ..domain.models import ProcessIdentity
from ..services.process_adapter import iter_process_records
from ..services.process_classifier import ProcessClassifier
from ..services.windows_process_adapter import (
    ProcessVerificationResult, ProcessVerificationStatus, WindowsProcessAdapter,
)
from .components import (
    Badge, DataTable, FilterBar, KeyValueList, MetricCard, PageScaffold,
    SectionCard, StatusBanner,
)

HEADERS = ["Process", "PID", "CPU", "Memory", "Status", "Category"]


def _record_to_dict(record):
    try:
        started = datetime.fromtimestamp(record.identity.create_time).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        started = "Unknown"
    return {
        "pid": record.identity.pid, "ppid": record.ppid,
        "name": record.identity.name, "exe": record.identity.exe or "",
        "username": record.username or "", "status": record.status or "Unknown",
        "cpu_percent": record.cpu_percent, "memory_rss": record.memory_rss,
        "memory_vms": record.memory_vms, "create_time": record.identity.create_time,
        "start_time": started, "num_threads": record.num_threads,
        "identity": record.identity,
    }


class ProcessLoadThread(QThread):
    batch_ready = Signal(object)
    classification_ready = Signal(int, object)
    completed = Signal(int)
    failed = Signal(str)

    def __init__(self, loader: Callable = None, classifier: Callable = None,
                 batch_size: int = 10, parent=None):
        super().__init__(parent)
        self._loader = loader or iter_process_records
        self._classifier = classifier or ProcessClassifier().classify
        self._batch_size = max(1, int(batch_size))

    def run(self):
        try:
            pending = []
            total = 0

            def classify_batch(batch):
                classified = []
                for process in batch:
                    if self.isInterruptionRequested():
                        return []
                    try:
                        result = self._classifier(process)
                    except Exception as exc:
                        result = {
                            "category": "Unknown / unverified", "risk_level": "Unknown",
                            "confidence": 0.0,
                            "explanation": "Classification unavailable: {}".format(exc),
                            "evidence": [], "can_terminate": False,
                        }
                    classified.append((process, result))
                return classified

            for record in self._loader():
                if self.isInterruptionRequested():
                    return
                pending.append(_record_to_dict(record))
                if len(pending) >= self._batch_size:
                    classified = classify_batch(pending)
                    if self.isInterruptionRequested():
                        return
                    if classified:
                        self.batch_ready.emit(classified)
                        total += len(classified)
                    pending = []

            if pending and not self.isInterruptionRequested():
                classified = classify_batch(pending)
                if classified:
                    self.batch_ready.emit(classified)
                    total += len(classified)

            if not self.isInterruptionRequested():
                self.completed.emit(total)
        except Exception as exc:
            self.failed.emit(str(exc))


class ProcessVerificationThread(QThread):
    completed = Signal(object, object)

    def __init__(self, identity, adapter=None, parent=None):
        super().__init__(parent)
        self.identity = identity
        self.adapter = adapter or WindowsProcessAdapter()

    def run(self):
        try:
            result = self.adapter.inspect(self.identity)
        except Exception as exc:
            result = ProcessVerificationResult(
                ProcessVerificationStatus.QUERY_FAILED, self.identity, detail=str(exc)
            )
        self.completed.emit(self.identity, result)


class ProcessTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return HEADERS[section]
        return None

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def append_rows(self, rows):
        rows = list(rows)
        if not rows:
            return
        first, last = len(self._rows), len(self._rows) + len(rows) - 1
        self.beginInsertRows(QModelIndex(), first, last)
        self._rows.extend(rows)
        self.endInsertRows()

    def update_classifications(self, start, rows):
        if not rows or start < 0 or start >= len(self._rows):
            return
        end = min(start + len(rows), len(self._rows))
        self._rows[start:end] = list(rows)[:end - start]
        self.dataChanged.emit(self.index(start, 5), self.index(end - 1, 5),
                              [Qt.DisplayRole, Qt.ToolTipRole, Qt.UserRole])

    def row(self, index):
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        process, classification = self._rows[index.row()]
        values = (
            process.get("name") or "Unknown process", process.get("pid"),
            process.get("cpu_percent"), process.get("memory_rss"),
            process.get("status") or "Unavailable",
            classification.get("category", "Unknown / unverified"),
        )
        if role == Qt.UserRole:
            return values[index.column()]
        if role == Qt.DisplayRole:
            col, value = index.column(), values[index.column()]
            if col == 1:
                return str(value)
            if col == 2:
                return "—" if value is None else "{:.1f}%".format(value)
            if col == 3:
                return "—" if value is None else "{:.1f} MiB".format(value / (1024 * 1024))
            return value
        if role == Qt.ToolTipRole:
            if index.column() == 0:
                return process.get("exe") or "Executable path unavailable"
            if index.column() == 5:
                return "{}\n{}".format(classification.get("risk_level", "Unknown"),
                                         classification.get("explanation", ""))
        return None


class ProcessFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.search_text, self.filter_type = "", "All user applications"
        self.setDynamicSortFilter(False)

    def set_criteria(self, search_text, filter_type):
        self.search_text = (search_text or "").strip().casefold()
        self.filter_type = filter_type
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        pair = self.sourceModel().row(source_row)
        if pair is None:
            return False
        process, classification = pair
        name, exe = (process.get("name") or "").casefold(), (process.get("exe") or "").casefold()
        # Version 1 is application-focused: never expose system, protected,
        # background/unknown or unclassified processes in the normal view.
        if classification.get("category") != "User application":
            return False
        if self.search_text and self.search_text not in name and self.search_text not in exe:
            return False
        if self.filter_type == "High Memory (>100 MiB)":
            value = process.get("memory_rss")
            if value is None or value <= 100 * 1024 * 1024:
                return False
        if self.filter_type == "High CPU (>10%)":
            value = process.get("cpu_percent")
            if value is None or value <= 10:
                return False
        return True

    def lessThan(self, left, right):
        a = self.sourceModel().data(left, Qt.UserRole)
        b = self.sourceModel().data(right, Qt.UserRole)
        if a is None:
            return b is not None
        if b is None:
            return False
        if isinstance(a, str) and isinstance(b, str):
            return a.casefold() < b.casefold()
        return a < b


class ProcessesScreen(QWidget):
    def __init__(self, process_loader=None, process_verifier=None):
        super().__init__()
        self.setObjectName("processesScreen")
        self._process_loader = process_loader or iter_process_records
        self._process_verifier = process_verifier
        self._load_thread = None
        self._verification_threads = set()
        self._all_rows = []
        self._snapshot_started = False
        self._loading = False
        self._pending_identity = None
        self.selected_identity = None
        self._build_ui()
        self.refresh_timer = self.startTimer(12000)
        self.refresh()

    # -- construction -----------------------------------------------------

    def _metric(self, layout, title, detail, accessible_name):
        card = MetricCard(title, "—", detail, progress_visible=False)
        card.title_label.setAccessibleName(f"{title} metric")
        card.value_label.setAccessibleName(accessible_name)
        layout.addWidget(card)
        return card

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scaffold = PageScaffold(
            "Processes",
            "Review running user-application candidates and their resource usage.",
            margins=20,
            spacing=14,
        )
        outer.addWidget(self.scaffold)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.process_count_card = self._metric(
            metrics, "Applications", "User-application candidates",
            "Number of user-application candidates",
        )
        self.cpu_card = self._metric(
            metrics, "Process CPU total", "Sum across visible applications",
            "Total process CPU usage",
        )
        self.memory_card = self._metric(
            metrics, "Process memory total", "Working sets may double-count shared pages",
            "Total process memory usage",
        )
        self.process_count_value = self.process_count_card.value_label
        self.cpu_value = self.cpu_card.value_label
        self.memory_value = self.memory_card.value_label
        self.cpu_value.setToolTip(
            "Sum of process CPU percentages; may exceed 100% on multicore systems."
        )
        self.memory_value.setToolTip(
            "Sum of working sets; shared pages can be counted more than once."
        )
        self.scaffold.add_layout(metrics)

        self.filter_bar = FilterBar("Search applications…")
        self.search_input = self.filter_bar.search_edit
        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            "All user applications",
            "High Memory (>100 MiB)",
            "High CPU (>10%)",
        ])
        self.filter_combo.setAccessibleName("Filter processes")
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setAccessibleName("Refresh process list")
        self.refresh_btn.clicked.connect(self.refresh)
        self.filter_bar.add_widget(self.filter_combo, 1)
        self.filter_bar.add_widget(self.refresh_btn)
        self.scaffold.add_widget(self.filter_bar)

        self.status_banner = StatusBanner(
            "Preparing process monitor…", "loading"
        )
        self.status_label = self.status_banner.message_label
        self.scaffold.add_widget(self.status_banner)

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(140)
        self._filter_timer.timeout.connect(self._apply_filters)
        self.search_input.textChanged.connect(lambda *_: self._filter_timer.start())
        self.filter_bar.search_changed.connect(lambda *_: self._filter_timer.start())
        self.filter_combo.currentTextChanged.connect(self._apply_filters)

        splitter = QSplitter(Qt.Horizontal)
        self.table = DataTable()
        self.table.setObjectName("processTable")
        self.model = ProcessTableModel(self)
        self.proxy = ProcessFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.table.setModel(self.proxy)
        self.table.configure_columns(stretch=(0,), numeric=(1, 2, 3))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        for col, width in ((1, 78), (2, 86), (3, 112), (4, 92), (5, 176)):
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, width)
        self.table.setAlternatingRowColors(True)
        self.table.setAccessibleName("Running user applications")
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.table.error_state.retry_requested.connect(self.refresh)
        splitter.addWidget(self.table)
        splitter.addWidget(self._build_details())
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        self.scaffold.add_widget(splitter, 1)

    def _build_details(self):
        self.details_card = SectionCard(
            "Application details",
            "Read-only information. Process actions remain unavailable in this version.",
        )
        self.details_name = QLabel("Select an application")
        self.details_name.setObjectName("sectionTitle")
        self.details_name.setWordWrap(True)
        self.details_name.setAccessibleName("Selected application")
        self.details_badge = Badge("No selection", "neutral")
        self.risk_badge = Badge("Risk unknown", "neutral")

        badges = QHBoxLayout()
        badges.setSpacing(8)
        badges.addWidget(self.details_badge)
        badges.addWidget(self.risk_badge)
        badges.addStretch()

        self.details = KeyValueList()
        for key in ("PID", "User", "Status", "CPU", "Memory", "Category",
                    "Risk", "Executable"):
            self.details.add_row(key, "—")
        self.details_text = QLabel("Select an application to inspect resource usage.")
        self.details_text.setObjectName("pageSubtitle")
        self.details_text.setWordWrap(True)
        self.details_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.verification_label = QLabel(
            "Identity verification has not been requested."
        )
        self.verification_label.setObjectName("pageSubtitle")
        self.verification_label.setWordWrap(True)
        self.verification_label.setAccessibleName("Process identity verification")

        self.action_notice = StatusBanner(
            "Application closing is not enabled yet. A user-application "
            "classification does not prove that closing is consequence-free.",
            "warning",
        )
        self.close_btn, self.force_kill_btn = (
            QPushButton("Close application"), QPushButton("Force stop")
        )
        # Force stop is intentionally absent from the Version 1 interface.
        self.force_kill_btn.hide()
        for button in (self.close_btn, self.force_kill_btn):
            button.setEnabled(False)
            button.setToolTip(
                "Unavailable until the graceful-close safety and verification "
                "work is complete."
            )
            button.clicked.connect(self._explain_actions_unavailable)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.close_btn)
        actions.addWidget(self.force_kill_btn)
        actions.addStretch()

        self.details_card.add_widget(self.details_name)
        self.details_card.add_layout(badges)
        self.details_body = QWidget()
        self.details_body.setMinimumSize(0, 0)
        body_layout = QVBoxLayout(self.details_body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)
        body_layout.addWidget(self.details)
        body_layout.addWidget(self.details_text)
        body_layout.addWidget(self.verification_label)
        body_layout.addWidget(self.action_notice)
        body_layout.addLayout(actions)
        body_layout.addStretch()
        self.details_scroll = QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setMinimumSize(0, 0)
        self.details_scroll.setAccessibleName("Application details")
        self.details_scroll.setWidget(self.details_body)
        self.details_card.add_widget(self.details_scroll, 1)
        return self.details_card

    # -- loading and state ------------------------------------------------

    def timerEvent(self, event):
        if event.timerId() == self.refresh_timer:
            self.refresh()
        else:
            super().timerEvent(event)

    def refresh(self):
        if self._load_thread is not None and self._load_thread.isRunning():
            return
        self.refresh_btn.setEnabled(False)
        self._loading = True
        self.status_banner.set_state("loading", "Loading process information…")
        self.table.set_state("loading", "Loading process information…")
        self._pending_identity = self.selected_identity
        self._snapshot_started = False
        thread = ProcessLoadThread(self._process_loader, parent=self)
        thread.batch_ready.connect(self._on_process_batch)
        thread.classification_ready.connect(self._on_classification_batch)
        thread.completed.connect(self._on_loading_complete)
        thread.failed.connect(self._on_processes_failed)
        thread.finished.connect(lambda: self._load_finished(thread))
        self._load_thread = thread
        thread.start()

    def _load_finished(self, thread):
        if self._load_thread is thread:
            self._load_thread = None
        self.refresh_btn.setEnabled(True)
        thread.deleteLater()

    def _on_process_batch(self, batch):
        if not self._snapshot_started:
            self._snapshot_started = True
            self._all_rows = []
            self.model.set_rows([])
        self._all_rows.extend(batch)
        self.model.append_rows(batch)
        self._apply_filters()
        self.table.set_state("ready")
        self._update_metrics()
        self.status_banner.set_state("info", "Scanning applications…")

    def _on_classification_batch(self, start, rows):
        for offset, row in enumerate(rows):
            if start + offset < len(self._all_rows):
                self._all_rows[start + offset] = row
        self.model.update_classifications(start, rows)
        self.proxy.invalidateFilter()
        self._update_metrics()
        self._update_visible_state()

    def _on_loading_complete(self, count):
        if not self._snapshot_started:
            self._snapshot_started = True
            self._all_rows = []
            self.model.set_rows([])
        self._loading = False
        self._apply_filters()
        self._update_metrics()
        applications = sum(
            1 for _, classification in self._all_rows
            if classification.get("category") == "User application"
        )
        self.status_banner.set_state(
            "success", "Updated · {:,} applications".format(applications)
        )
        self._update_visible_state()
        if self._pending_identity is not None:
            self._restore_selection(self._pending_identity)
        self._pending_identity = None

    def _on_processes_failed(self, message):
        self._loading = False
        if self._snapshot_started and self._all_rows:
            self.status_banner.set_state(
                "warning", "Partial process list · refresh failed: {}".format(message)
            )
            self._update_visible_state()
        else:
            self.status_banner.set_state(
                "error", "Refresh failed · existing process list retained"
            )
            self.table.set_state("error", message)
            self.table.error_state.set_description(str(message))
            self.details_name.setText("Process list unavailable")
            self.details_text.setText(message)

    def _apply_filters(self, *_):
        self.proxy.set_criteria(self.search_input.text(), self.filter_combo.currentText())
        self._update_visible_state()

    def _update_visible_state(self):
        if self._loading:
            return
        if not self._all_rows:
            self.table.set_state("empty", "No user applications were found")
        elif self.proxy.rowCount() == 0:
            self.table.set_state("empty", "No matching applications")
        else:
            self.table.set_state("ready")

    def _update_metrics(self):
        # Totals describe only the user-application candidates visible in V1.
        applications = [
            row for row in self._all_rows
            if row[1].get("category") == "User application"
        ]
        self.process_count_value.setText("{:,}".format(len(applications)))
        cpus = [
            r[0].get("cpu_percent") for r in applications
            if r[0].get("cpu_percent") is not None
        ]
        mems = [
            r[0].get("memory_rss") for r in applications
            if r[0].get("memory_rss") is not None
        ]
        self.cpu_value.setText("{:.1f}%".format(sum(cpus)) if cpus else "—")
        self.memory_value.setText("{:.1f} MiB".format(sum(mems) / (1024 * 1024)))

    # -- selection --------------------------------------------------------

    def _restore_selection(self, identity):
        for row in range(self.proxy.rowCount()):
            source = self.proxy.mapToSource(self.proxy.index(row, 0))
            pair = self.model.row(source.row())
            if pair and pair[0].get("identity") == identity:
                self.table.selectRow(row)
                return
        self.selected_identity = None
        self.details_name.setText("Select a process")
        self.details_text.setText(
            "The previously selected process is no longer present."
        )
        self.verification_label.setText(
            "Selection cleared: process identity no longer exists."
        )
        self.details_badge.set_text("No selection")
        self.details_badge.set_status("neutral")
        self.risk_badge.set_text("Risk unknown")
        self.risk_badge.set_status("neutral")
        for key in self.details.keys():
            self.details.set_value(key, "—")

    def _selection_changed(self, *_):
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return
        source = self.proxy.mapToSource(indexes[0])
        pair = self.model.row(source.row())
        if pair is None:
            return
        process, classification = pair
        identity = process.get("identity")
        if not isinstance(identity, ProcessIdentity):
            self.selected_identity = None
            return
        self.selected_identity = identity
        cpu, memory = process.get("cpu_percent"), process.get("memory_rss")
        category = classification.get("category", "Unknown")
        risk = classification.get("risk_level", "Unknown")
        self.details_name.setText(
            "{} · PID {}".format(process.get("name"), identity.pid)
        )
        self.details_badge.set_text(category)
        self.details_badge.set_status(
            "info" if category == "User application" else "warning"
        )
        self.risk_badge.set_text("Risk: {}".format(risk))
        self.risk_badge.set_status(
            "critical" if "High" in risk else "warning" if risk != "Unknown" else "neutral"
        )
        self.details.set_value("PID", str(identity.pid))
        self.details.set_value("User", process.get("username") or "Unavailable")
        self.details.set_value("Status", process.get("status") or "Unavailable")
        self.details.set_value(
            "CPU", "Unavailable" if cpu is None else "{:.1f}%".format(cpu)
        )
        self.details.set_value(
            "Memory",
            "Unavailable" if memory is None else "{:.1f} MiB".format(memory / (1024 * 1024)),
        )
        self.details.set_value("Category", category)
        self.details.set_value("Risk", risk)
        self.details.set_value("Executable", process.get("exe") or "Unavailable")
        self.details_text.setText(classification.get("explanation", ""))
        self.verification_label.setText(
            "Verifying this process instance against Windows…"
        )
        thread = ProcessVerificationThread(identity, adapter=self._process_verifier, parent=self)
        thread.completed.connect(self._on_identity_verified)
        thread.finished.connect(lambda: self._verification_finished(thread))
        self._verification_threads.add(thread)
        thread.start()

    def _on_identity_verified(self, identity, result):
        if identity != self.selected_identity:
            return
        status = getattr(getattr(result, "status", None), "value", "verification_failed")
        self.verification_label.setText(
            "Identity: {}\n{}".format(
                status.replace("_", " ").title(), getattr(result, "detail", "")
            )
        )

    def _verification_finished(self, thread):
        self._verification_threads.discard(thread)
        thread.deleteLater()

    def _explain_actions_unavailable(self):
        QMessageBox.information(self, "Process actions unavailable",
            "Process actions remain disabled until identity-safe authorization and verified action handling are complete.")

    def closeEvent(self, event):
        if self._load_thread is not None and self._load_thread.isRunning():
            self._load_thread.requestInterruption()
            self._load_thread.wait(2000)
        for thread in tuple(self._verification_threads):
            if thread.isRunning():
                thread.requestInterruption()
                thread.wait(1000)
        super().closeEvent(event)
