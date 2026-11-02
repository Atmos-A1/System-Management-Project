"""Storage Insights UI and background analysis worker."""

import os
import threading

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..services.storage_analysis import StorageAnalysis
from .table_models import (
    PERCENT_ROLE,
    ColumnSpec,
    DistributionDelegate,
    RecordFilterProxyModel,
    RecordTableModel,
    RecordTableView,
    format_size,
)


_ACTIVE_THREADS = set()


def _format_size(value):
    try:
        number = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return "0 B"
    if number < 1024:
        return f"{number} B"
    units = ["KB", "MB", "GB", "TB", "PB"]
    size = float(number)
    for unit in units:
        size /= 1024.0
        if size < 1024:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} EB"


def _status_label(status):
    text = str(status or "unknown")
    return text.capitalize()


def _failed_result(roots, error):
    return {
        "roots": list(roots),
        "status": "failed",
        "complete": False,
        "partial": False,
        "cancelled": False,
        "failed": True,
        "total_size": 0,
        "file_count": 0,
        "directory_count": 0,
        "skipped_count": 0,
        "excluded_links": 0,
        "duplicate_objects": 0,
        "folders": [],
        "file_types": [],
        "root_summaries": [],
        "errors": [],
        "error": str(error),
        "elapsed_seconds": 0.0,
    }


class _AnalysisWorker(QObject):
    progress = Signal(dict)
    finished = Signal(dict)

    def __init__(self, generation, roots, service, parent=None):
        super().__init__(parent)
        self.generation = generation
        self.roots = list(roots)
        self.service = service
        self._cancel_event = threading.Event()

    def request_cancel(self):
        self._cancel_event.set()

    def _on_progress(self, payload):
        item = dict(payload)
        item["generation"] = self.generation
        self.progress.emit(item)

    def run(self):
        try:
            result = self.service.analyze(
                self.roots,
                cancel_event=self._cancel_event,
                progress_callback=self._on_progress,
            )
        except Exception as exc:
            result = _failed_result(self.roots, exc)
        result["generation"] = self.generation
        self.finished.emit(result)


class _AnalysisThread(QThread):
    def __init__(self, worker):
        super().__init__()
        self.worker = worker

    def run(self):
        self.worker.run()


class InsightsWidget(QWidget):
    """Informational folder-size and file-type analysis view."""

    folder_opened = Signal(str)

    def __init__(self, initial_path=None, service=None, parent=None):
        super().__init__(parent)
        self.setObjectName("storageInsights")
        self.setStyleSheet("background-color: transparent;")
        self.service = service or StorageAnalysis()
        self._current_result = None
        self._generation = 0
        self._thread = None
        self._worker = None
        self._pending = None
        self._running = False
        self._shutting_down = False

        self._build_ui()
        self.destroyed.connect(self._on_destroyed)
        self.path_input.setText(
            os.path.abspath(
                os.path.expanduser(initial_path or "~")
            )
        )

    @property
    def current_result(self):
        return self._current_result

    @property
    def is_running(self):
        return self._running

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QLabel("Insights")
        header.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #111827;"
        )
        layout.addWidget(header)

        sub = QLabel(
            "Analyze folder sizes and file-type distribution without "
            "changing files."
        )
        sub.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(sub)

        self.read_only_label = QLabel(
            "Insights are informational and never authorize cleanup."
        )
        self.read_only_label.setStyleSheet(
            "background-color: #eff6ff; border: 1px solid #bfdbfe; "
            "border-radius: 6px; padding: 7px 10px; color: #1e40af; "
            "font-size: 11px;"
        )
        layout.addWidget(self.read_only_label)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        path_label = QLabel("Analysis Path:")
        path_label.setStyleSheet("color: #374151;")
        controls.addWidget(path_label)
        self.path_input = QLineEdit()
        self.path_input.setMinimumWidth(280)
        controls.addWidget(self.path_input, 1)
        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.setStyleSheet(
            "padding: 7px 14px; border-radius: 6px; "
            "background-color: #2563eb; color: #ffffff; border: none;"
        )
        controls.addWidget(self.analyze_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setStyleSheet(
            "padding: 7px 12px; border-radius: 6px; "
            "background-color: #f3f4f6; color: #111827; "
            "border: 1px solid #d1d5db;"
        )
        self.cancel_button.setVisible(False)
        controls.addWidget(self.cancel_button)
        layout.addLayout(controls)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: none; background-color: #f1f5f9; "
            "border-radius: 3px; } "
            "QProgressBar::chunk { background-color: #2563eb; "
            "border-radius: 3px; }"
        )
        status_row.addWidget(self.progress_bar, 1)
        self.status_label = QLabel("No analysis yet.")
        self.status_label.setStyleSheet(
            "color: #374151; font-size: 11px;"
        )
        status_row.addWidget(self.status_label, 3)
        layout.addLayout(status_row)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "background-color: #ffffff; border: 1px solid #e5e7eb; "
            "border-radius: 6px; padding: 8px; color: #374151; "
            "font-size: 11px;"
        )
        layout.addWidget(self.summary_label)

        self.analysis_tabs = QTabWidget()
        self.analysis_tabs.setDocumentMode(True)
        self.analysis_tabs.addTab(
            self._build_folder_tab(), "Folder Sizes"
        )
        self.analysis_tabs.addTab(
            self._build_file_type_tab(), "File Types"
        )
        layout.addWidget(self.analysis_tabs, 1)

        self.analyze_button.clicked.connect(self.start_analysis)
        self.cancel_button.clicked.connect(self.cancel_analysis)
        self.open_folder_button.clicked.connect(self._open_selected_folder)

    def _build_folder_tab(self):
        widget = QWidget()
        widget.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)
        self.folder_filter_input = QLineEdit()
        self.folder_filter_input.setPlaceholderText(
            "Filter folders by name or path"
        )
        self.folder_filter_input.setClearButtonEnabled(True)
        filter_layout.addWidget(self.folder_filter_input, 1)
        self.folder_filter_status = QLabel("")
        self.folder_filter_status.setStyleSheet(
            "color: #6b7280; font-size: 11px;"
        )
        filter_layout.addWidget(self.folder_filter_status)
        layout.addLayout(filter_layout)

        self.folder_model = RecordTableModel(
            [
                ColumnSpec(
                    "Folder",
                    lambda folder: folder.get("name", ""),
                    lambda folder: str(
                        folder.get("name", "")
                    ).casefold(),
                    lambda folder: folder.get("path", ""),
                ),
                ColumnSpec(
                    "Path",
                    lambda folder: folder.get("path", ""),
                    lambda folder: str(
                        folder.get("path", "")
                    ).casefold(),
                    lambda folder: folder.get("path", ""),
                ),
                ColumnSpec(
                    "Size",
                    lambda folder: format_size(folder.get("size")),
                    lambda folder: int(folder.get("size") or 0),
                ),
                ColumnSpec(
                    "Files",
                    lambda folder: str(folder.get("file_count", 0)),
                    lambda folder: int(folder.get("file_count") or 0),
                ),
                ColumnSpec(
                    "Status",
                    lambda folder: _status_label(folder.get("status")),
                    lambda folder: str(folder.get("status", "")),
                ),
            ],
            [],
            search_fields=("name", "path"),
        )
        self.folder_proxy = RecordFilterProxyModel()
        self.folder_proxy.setSourceModel(self.folder_model)
        self.folder_table = RecordTableView()
        self.folder_table.setModel(self.folder_proxy)
        self._configure_table(self.folder_table)
        self.folder_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.folder_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        for column in (2, 3, 4):
            self.folder_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )
        self.folder_table.sortByColumn(2, Qt.DescendingOrder)
        layout.addWidget(self.folder_table, 1)
        self.folder_filter_input.textChanged.connect(
            self._on_folder_filter_changed
        )

        actions = QHBoxLayout()
        actions.addStretch()
        self.open_folder_button = QPushButton("Open in Explorer")
        self.open_folder_button.setEnabled(False)
        self.open_folder_button.setStyleSheet(
            "padding: 7px 12px; border-radius: 6px; "
            "background-color: #f3f4f6; color: #111827; "
            "border: 1px solid #d1d5db;"
        )
        actions.addWidget(self.open_folder_button)
        layout.addLayout(actions)

        self.folder_table.itemSelectionChanged.connect(
            self._update_folder_action
        )
        self.folder_table.itemDoubleClicked.connect(
            self._open_folder_item
        )
        return widget

    def _build_file_type_tab(self):
        widget = QWidget()
        widget.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)
        self.file_type_filter_input = QLineEdit()
        self.file_type_filter_input.setPlaceholderText(
            "Filter file types by extension or label"
        )
        self.file_type_filter_input.setClearButtonEnabled(True)
        filter_layout.addWidget(self.file_type_filter_input, 1)
        self.file_type_filter_status = QLabel("")
        self.file_type_filter_status.setStyleSheet(
            "color: #6b7280; font-size: 11px;"
        )
        filter_layout.addWidget(self.file_type_filter_status)
        layout.addLayout(filter_layout)

        self.file_type_model = RecordTableModel(
            [
                ColumnSpec(
                    "Type",
                    lambda item: item.get("label", ""),
                    lambda item: str(item.get("label", "")).casefold(),
                    lambda item: item.get("key", ""),
                ),
                ColumnSpec(
                    "Files",
                    lambda item: str(item.get("count", 0)),
                    lambda item: int(item.get("count") or 0),
                ),
                ColumnSpec(
                    "Size",
                    lambda item: format_size(item.get("size")),
                    lambda item: int(item.get("size") or 0),
                ),
                ColumnSpec(
                    "Share",
                    lambda item: (
                        f"{float(item.get('percentage') or 0.0):.1f}%"
                    ),
                    lambda item: float(item.get("percentage") or 0.0),
                ),
                ColumnSpec(
                    "Distribution",
                    lambda item: (
                        f"{float(item.get('percentage') or 0.0):.1f}%"
                    ),
                    lambda item: float(item.get("percentage") or 0.0),
                ),
            ],
            [],
            search_fields=("label", "key"),
        )
        self.file_type_proxy = RecordFilterProxyModel()
        self.file_type_proxy.setSourceModel(self.file_type_model)
        self.file_type_table = RecordTableView()
        self.file_type_table.setModel(self.file_type_proxy)
        self._configure_table(self.file_type_table)
        self.file_type_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        for column in (1, 2, 3):
            self.file_type_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )
        self.file_type_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.Stretch
        )
        self.file_type_table.setItemDelegateForColumn(
            4, DistributionDelegate(self.file_type_table)
        )
        self.file_type_table.sortByColumn(2, Qt.DescendingOrder)
        layout.addWidget(self.file_type_table, 1)
        self.file_type_filter_input.textChanged.connect(
            self._on_file_type_filter_changed
        )
        return widget

    @staticmethod
    def _configure_table(table):
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setWordWrap(False)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setStyleSheet(
            "QTableView { background-color: #ffffff; "
            "border: 1px solid #e5e7eb; border-radius: 6px; "
            "gridline-color: #f3f4f6; } "
            "QHeaderView::section { background-color: #f9fafb; "
            "padding: 6px; border: none; "
            "border-right: 1px solid #e5e7eb; "
            "border-bottom: 1px solid #e5e7eb; font-weight: 600; }"
        )

    def start_analysis(self, path=None):
        raw = str(
            path if path is not None else self.path_input.text()
        ).strip()
        if not raw:
            self.status_label.setText("Enter a directory path to analyze.")
            return
        target = os.path.abspath(os.path.expanduser(raw))
        self.path_input.setText(target)
        self._generation += 1
        generation = self._generation
        self._clear_results()
        self._set_running(True)
        self.status_label.setText(f"Analyzing {target}...")

        if self._thread is not None:
            self._pending = (generation, target)
            if self._worker is not None:
                self._worker.request_cancel()
            self.status_label.setText(
                "Cancelling current analysis..."
            )
            return
        self._start(generation, target)

    def cancel_analysis(self):
        self._pending = None
        if self._worker is not None:
            self._worker.request_cancel()
            self.status_label.setText("Cancelling analysis...")

    def _start(self, generation, target):
        worker = _AnalysisWorker(
            generation, [target], self.service
        )
        thread = _AnalysisThread(worker)
        worker.progress.connect(
            self._on_progress, Qt.QueuedConnection
        )
        worker.finished.connect(
            self._on_result, Qt.QueuedConnection
        )
        thread.finished.connect(self._on_thread_finished)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda t=thread: _ACTIVE_THREADS.discard(t)
        )
        _ACTIVE_THREADS.add(thread)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _set_running(self, running):
        self._running = bool(running)
        self.progress_bar.setVisible(self._running)
        self.analyze_button.setEnabled(not self._running)
        self.path_input.setEnabled(not self._running)
        self.cancel_button.setVisible(self._running)
        self.cancel_button.setEnabled(self._running)

    def _clear_results(self):
        self._current_result = None
        self.folder_model.set_records([])
        self.file_type_model.set_records([])
        self.folder_table.clearSelection()
        self.file_type_table.clearSelection()
        self._update_folder_filter_status()
        self._update_file_type_filter_status()
        self.summary_label.setText("")
        self.open_folder_button.setEnabled(False)

    def _on_progress(self, payload):
        if payload.get("generation") != self._generation:
            return
        self.status_label.setText(
            "Analyzing: "
            f"{payload.get('files_scanned', 0)} files | "
            f"{payload.get('directories_scanned', 0)} folders | "
            f"{_format_size(payload.get('bytes_scanned', 0))}"
        )

    def _on_result(self, result):
        if result.get("generation") != self._generation:
            return
        self._running = False
        self.progress_bar.setVisible(False)
        self.analyze_button.setEnabled(True)
        self.path_input.setEnabled(True)
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(False)
        self._apply_result(result)

    def _apply_result(self, result):
        self._current_result = result
        folders = result.get("folders", []) or []
        file_types = result.get("file_types", []) or []
        self._populate_folders(folders)
        self._populate_file_types(file_types)

        roots = result.get("roots") or []
        root_text = ", ".join(roots) if roots else "—"
        self.summary_label.setText(
            f"Root: {root_text} | "
            f"Total: {_format_size(result.get('total_size', 0))} | "
            f"Files: {result.get('file_count', 0)} | "
            f"Folders: {result.get('directory_count', 0)} | "
            f"Skipped: {result.get('skipped_count', 0)}"
        )
        self.summary_label.setToolTip(self.summary_label.text())

        status = result.get("status", "failed")
        if status == "cancelled":
            self.status_label.setText("Analysis cancelled.")
        elif status == "failed":
            reason = (
                result.get("error")
                or self._first_error(result.get("errors") or [])
                or "Unknown error"
            )
            self.status_label.setText(f"Analysis failed: {reason}")
        elif status == "partial":
            self.status_label.setText(
                "Partial analysis: "
                f"{result.get('skipped_count', 0)} entries skipped."
            )
        elif not file_types and not folders:
            self.status_label.setText(
                "Analysis complete: no files found."
            )
        else:
            self.status_label.setText(
                f"Analysis complete: {result.get('file_count', 0)} "
                f"files across {len(folders)} folders."
            )

    @staticmethod
    def _first_error(errors):
        if errors and isinstance(errors[0], dict):
            return errors[0].get("error")
        return ""

    def _populate_folders(self, folders):
        self.folder_model.set_records(folders or [])
        self.folder_table.clearSelection()
        self.open_folder_button.setEnabled(False)
        self._update_folder_filter_status()

    def _populate_file_types(self, file_types):
        self.file_type_model.set_records(file_types or [])
        self._update_file_type_filter_status()

    def _on_folder_filter_changed(self, _text):
        self.folder_proxy.set_search_text(
            self.folder_filter_input.text()
        )
        self._update_folder_filter_status()

    def _update_folder_filter_status(self):
        active = bool(self.folder_filter_input.text().strip())
        total = self.folder_model.rowCount()
        visible = self.folder_proxy.rowCount()
        if not active:
            self.folder_filter_status.setText("")
        elif visible == 0:
            self.folder_filter_status.setText(
                "No folders match the current filter."
            )
        else:
            self.folder_filter_status.setText(
                f"Showing {visible} of {total} folders."
            )

    def _on_file_type_filter_changed(self, _text):
        self.file_type_proxy.set_search_text(
            self.file_type_filter_input.text()
        )
        self._update_file_type_filter_status()

    def _update_file_type_filter_status(self):
        active = bool(self.file_type_filter_input.text().strip())
        total = self.file_type_model.rowCount()
        visible = self.file_type_proxy.rowCount()
        if not active:
            self.file_type_filter_status.setText("")
        elif visible == 0:
            self.file_type_filter_status.setText(
                "No file types match the current filter."
            )
        else:
            self.file_type_filter_status.setText(
                f"Showing {visible} of {total} types."
            )

    def _update_folder_action(self):
        self.open_folder_button.setEnabled(
            self.folder_table.currentIndex().isValid()
        )

    def _open_folder_item(self, item):
        if hasattr(item, "isValid") and item.isValid():
            index = item
        else:
            model = self.folder_table.model()
            index = model.index(item.row(), 0) if model is not None else None
        if index is None:
            return
        self.folder_table.setCurrentIndex(index)
        self._open_selected_folder()

    def _open_selected_folder(self):
        index = self.folder_table.currentIndex()
        folder = self.folder_table.record_for_index(index)
        if folder is None:
            return
        path = folder.get("path")
        if path:
            self.folder_opened.emit(str(path))

    def _on_thread_finished(self):
        thread = self.sender()
        if thread is not self._thread:
            return
        self._thread = None
        self._worker = None
        if self._shutting_down:
            self._running = False
            self.progress_bar.setVisible(False)
            return
        if self._pending is not None:
            generation, target = self._pending
            self._pending = None
            self._start(generation, target)

    def shutdown(self, timeout_ms=1000):
        stopped = self._stop_worker(timeout_ms)
        if stopped:
            self._running = False
            self.progress_bar.setVisible(False)
        return stopped

    def _stop_worker(self, timeout_ms=1000):
        self._shutting_down = True
        self._pending = None
        self._generation += 1
        if self._worker is not None:
            self._worker.request_cancel()
        thread = self._thread
        if thread is None:
            return True
        if not thread.wait(timeout_ms):
            return False
        self._thread = None
        self._worker = None
        return True

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    def _on_destroyed(self, *_args):
        self._stop_worker(timeout_ms=1000)
