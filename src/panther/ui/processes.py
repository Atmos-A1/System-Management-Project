"""Responsive Process Explorer with background discovery and identity-aware selection."""
from datetime import datetime
from typing import Callable

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QThread,
    QTimer, Qt, Signal,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSplitter, QTableView, QVBoxLayout,
    QWidget,
)

from ..domain.models import ProcessIdentity
from ..services.process_adapter import iter_process_records
from ..services.process_classifier import ProcessClassifier
from ..services.windows_process_adapter import (
    ProcessVerificationResult, ProcessVerificationStatus, WindowsProcessAdapter,
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
                 batch_size: int = 50, parent=None):
        super().__init__(parent)
        self._loader = loader or iter_process_records
        self._classifier = classifier or ProcessClassifier().classify
        self._batch_size = max(1, int(batch_size))

    def run(self):
        try:
            rows, pending = [], []
            for record in self._loader():
                if self.isInterruptionRequested():
                    return
                process = _record_to_dict(record)
                placeholder = {
                    "category": "Classifying…", "risk_level": "Not assessed",
                    "confidence": 0.0, "explanation": "Classification is pending.",
                    "evidence": [], "can_terminate": False,
                }
                pair = (process, placeholder)
                rows.append(pair)
                pending.append(pair)
                if len(pending) >= self._batch_size:
                    self.batch_ready.emit(pending)
                    pending = []
            if pending:
                self.batch_ready.emit(pending)
            for start in range(0, len(rows), self._batch_size):
                if self.isInterruptionRequested():
                    return
                updated = []
                for process, _ in rows[start:start + self._batch_size]:
                    try:
                        result = self._classifier(process)
                    except Exception as exc:
                        result = {
                            "category": "Unknown / unverified", "risk_level": "Unknown",
                            "confidence": 0.0, "explanation": "Classification unavailable: {}".format(exc),
                            "evidence": [], "can_terminate": False,
                        }
                    updated.append((process, result))
                self.classification_ready.emit(start, updated)
            self.completed.emit(len(rows))
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
        self._pending_identity = None
        self.selected_identity = None
        self._build_ui()
        self.refresh_timer = self.startTimer(12000)
        self.refresh()

    def _build_ui(self):
        self.setStyleSheet("""
          QWidget#processesScreen {background:#f5f7fb;color:#172033}
          QFrame#card {background:white;border:1px solid #e4e9f1;border-radius:9px}
          QLabel#title {font-size:22px;font-weight:700}
          QLabel#muted {color:#68758a}
          QLineEdit,QComboBox {background:white;border:1px solid #d8dfeb;border-radius:7px;padding:8px}
          QPushButton {background:#2458c6;color:white;border:0;border-radius:7px;padding:8px 14px}
          QPushButton:disabled {background:#aab5c6}
          QTableView {background:white;alternate-background-color:#f8faff;border:1px solid #e4e9f1;
            selection-background-color:#e3edff;selection-color:#172033;outline:0}
          QHeaderView::section {background:#f2f5fa;border:0;padding:9px;font-weight:600}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        top = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Applications")
        title.setObjectName("title")
        subtitle = QLabel("Review running user-application candidates and their resource usage.")
        subtitle.setObjectName("muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        top.addLayout(titles)
        top.addStretch()
        self.status_label = QLabel("Preparing process monitor…")
        self.status_label.setObjectName("muted")
        top.addWidget(self.status_label)
        layout.addLayout(top)

        metrics = QHBoxLayout()
        self.process_count_value = self._metric(metrics, "Applications")
        self.cpu_value = self._metric(metrics, "Process CPU total")
        self.memory_value = self._metric(metrics, "Process memory total")
        self.cpu_value.setToolTip("Sum of process CPU percentages; may exceed 100% on multicore systems.")
        self.memory_value.setToolTip("Sum of working sets; shared pages can be counted more than once.")
        layout.addLayout(metrics)

        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search applications…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setAccessibleName("Search applications")
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All user applications",
                                    "High Memory (>100 MiB)", "High CPU (>10%)"])
        self.filter_combo.setAccessibleName("Filter processes")
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.search_input, 3)
        toolbar.addWidget(self.filter_combo, 1)
        toolbar.addWidget(self.refresh_btn)
        layout.addLayout(toolbar)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(140)
        self._filter_timer.timeout.connect(self._apply_filters)
        self.search_input.textChanged.connect(lambda *_: self._filter_timer.start())
        self.filter_combo.currentTextChanged.connect(self._apply_filters)

        splitter = QSplitter(Qt.Horizontal)
        self.table = QTableView()
        self.table.setObjectName("processTable")
        self.model = ProcessTableModel(self)
        self.proxy = ProcessFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.table.setModel(self.proxy)
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
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, width in ((1, 78), (2, 86), (3, 112), (4, 92), (5, 176)):
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, width)
        self.table.setAlternatingRowColors(True)
        self.table.setAccessibleName("Running user applications")
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        splitter.addWidget(self.table)

        details = QFrame()
        details.setObjectName("card")
        dlayout = QVBoxLayout(details)
        dlayout.setContentsMargins(14, 14, 14, 14)
        self.details_name = QLabel("Select an application")
        self.details_name.setWordWrap(True)
        self.details_text = QLabel("Select an application to inspect resource usage, executable and classification.")
        self.details_text.setWordWrap(True)
        self.details_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.verification_label = QLabel("Identity verification has not been requested.")
        self.verification_label.setWordWrap(True)
        self.action_notice = QLabel("Application closing is not enabled yet. A user-application classification does not prove that closing is consequence-free.")
        self.action_notice.setWordWrap(True)
        self.close_btn, self.force_kill_btn = QPushButton("Close application"), QPushButton("Force stop")
        # Force stop is intentionally absent from the Version 1 interface.
        self.force_kill_btn.hide()
        for button in (self.close_btn, self.force_kill_btn):
            button.setEnabled(False)
            button.setToolTip("Unavailable until the graceful-close safety and verification work is complete.")
            button.clicked.connect(self._explain_actions_unavailable)
        for widget in (self.details_name, self.details_text, self.verification_label,
                       self.action_notice, self.close_btn, self.force_kill_btn):
            dlayout.addWidget(widget)
        dlayout.addStretch()
        splitter.addWidget(details)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

    def _metric(self, layout, label):
        card = QFrame()
        card.setObjectName("card")
        box = QVBoxLayout(card)
        caption, value = QLabel(label), QLabel("—")
        caption.setObjectName("muted")
        value.setStyleSheet("font-size:19px;font-weight:700")
        box.addWidget(caption)
        box.addWidget(value)
        layout.addWidget(card)
        return value

    def timerEvent(self, event):
        if event.timerId() == self.refresh_timer:
            self.refresh()
        else:
            super().timerEvent(event)

    def refresh(self):
        if self._load_thread is not None and self._load_thread.isRunning():
            return
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("Loading process information…")
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
        self._update_metrics()
        self.status_label.setText("Scanning applications…")

    def _on_classification_batch(self, start, rows):
        for offset, row in enumerate(rows):
            if start + offset < len(self._all_rows):
                self._all_rows[start + offset] = row
        self.model.update_classifications(start, rows)
        self.proxy.invalidateFilter()
        self._update_metrics()

    def _on_loading_complete(self, count):
        if not self._snapshot_started:
            self._snapshot_started = True
            self._all_rows = []
            self.model.set_rows([])
        self._apply_filters()
        self._update_metrics()
        self.status_label.setText("Updated · {:,} applications".format(sum(1 for _, c in self._all_rows if c.get("category") == "User application")))
        if self._pending_identity is not None:
            self._restore_selection(self._pending_identity)
        self._pending_identity = None

    def _on_processes_failed(self, message):
        if self._snapshot_started:
            self.status_label.setText("Partial process list · refresh failed")
        else:
            self.status_label.setText("Refresh failed · existing process list retained")
        if not self._all_rows:
            self.details_name.setText("Process list unavailable")
            self.details_text.setText(message)

    def _apply_filters(self, *_):
        self.proxy.set_criteria(self.search_input.text(), self.filter_combo.currentText())

    def _update_metrics(self):
        # Totals describe only the user-application candidates visible in V1.
        applications = [row for row in self._all_rows if row[1].get("category") == "User application"]
        self.process_count_value.setText("{:,}".format(len(applications)))
        cpus = [r[0].get("cpu_percent") for r in applications if r[0].get("cpu_percent") is not None]
        mems = [r[0].get("memory_rss") for r in applications if r[0].get("memory_rss") is not None]
        self.cpu_value.setText("{:.1f}%".format(sum(cpus)) if cpus else "—")
        self.memory_value.setText("{:.0f} MiB".format(sum(mems) / (1024 * 1024)))

    def _restore_selection(self, identity):
        for row in range(self.proxy.rowCount()):
            source = self.proxy.mapToSource(self.proxy.index(row, 0))
            pair = self.model.row(source.row())
            if pair and pair[0].get("identity") == identity:
                self.table.selectRow(row)
                return
        self.selected_identity = None
        self.details_name.setText("Select a process")
        self.details_text.setText("The previously selected process is no longer present.")
        self.verification_label.setText("Selection cleared: process identity no longer exists.")

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
        self.details_name.setText("{} · PID {}".format(process.get("name"), identity.pid))
        self.details_text.setText(
            "User: {user}\nStatus: {status}\nCPU: {cpu}\nMemory: {memory}\n"
            "Category: {category}\nRisk: {risk}\nExecutable: {exe}\n\n{explanation}".format(
                user=process.get("username") or "Unavailable",
                status=process.get("status") or "Unavailable",
                cpu="Unavailable" if cpu is None else "{:.1f}%".format(cpu),
                memory="Unavailable" if memory is None else "{:.1f} MiB".format(memory / (1024 * 1024)),
                category=classification.get("category", "Unknown"),
                risk=classification.get("risk_level", "Unknown"),
                exe=process.get("exe") or "Unavailable",
                explanation=classification.get("explanation", ""),
            )
        )
        self.verification_label.setText("Verifying this process instance against Windows…")
        thread = ProcessVerificationThread(identity, adapter=self._process_verifier, parent=self)
        thread.completed.connect(self._on_identity_verified)
        thread.finished.connect(lambda: self._verification_finished(thread))
        self._verification_threads.add(thread)
        thread.start()

    def _on_identity_verified(self, identity, result):
        if identity != self.selected_identity:
            return
        status = getattr(getattr(result, "status", None), "value", "verification_failed")
        self.verification_label.setText("Identity: {}\n{}".format(status.replace("_", " ").title(),
                                                                     getattr(result, "detail", "")))

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
