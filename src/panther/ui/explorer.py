"""Read-only Storage Explorer UI.

The Explorer lists one directory at a time on a background thread. It never
opens, executes, follows links into, or cleans up filesystem entries.
"""

import os
import threading

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..services.directory_browser import DEFAULT_LIST_LIMIT, DirectoryBrowser
from ..services.file_inspector import FileInspector
from .table_models import (
    ColumnSpec,
    RecordFilterProxyModel,
    RecordTableModel,
    RecordTableView,
    format_size,
)


_ACTIVE_THREADS = set()


_MATCH_LABELS = {
    "match": "Extension matches signature",
    "mismatch": "Extension does not match signature",
    "unavailable": "Extension unavailable",
    "unknown": "No conclusion",
}


def _match_label(value):
    return _MATCH_LABELS.get(str(value or ""), "No conclusion")


def _error_inspection_result(path, exc):
    message = str(exc) or "Inspection failed"
    return {
        "cancelled": False,
        "metadata": {
            "ok": False,
            "path": path,
            "name": os.path.basename(path),
            "entry_type": None,
            "error": message,
            "error_kind": "os",
        },
        "signature": {
            "ok": False,
            "status": "unreadable",
            "format": None,
            "format_label": None,
            "error": message,
            "error_kind": "os",
            "extension_match": "unknown",
        },
    }

_TYPE_LABELS = {
    "directory": "Folder",
    "file": "File",
    "link": "Link",
    "reparse": "Reparse point",
    "other": "Other",
}

_SORT_TYPE_ORDER = {
    "directory": 0,
    "file": 1,
    "link": 2,
    "reparse": 3,
    "other": 4,
}


def _size_sort_key(entry):
    value = entry.get("size")
    if value is None:
        return -1
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _format_size(value):
    if value is None:
        return "—"
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return "—"
    if number < 1024:
        return f"{number} B"
    units = ["KB", "MB", "GB", "TB", "PB"]
    size = float(number)
    for unit in units:
        size /= 1024.0
        if size < 1024:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} EB"


class _DirectoryWorker(QObject):
    finished = Signal(dict)

    def __init__(self, generation, path, browser, limit, parent=None):
        super().__init__(parent)
        self.generation = generation
        self.path = path
        self.browser = browser
        self.limit = limit
        self._cancel_event = threading.Event()

    def request_cancel(self):
        self._cancel_event.set()

    def run(self):
        try:
            result = self.browser.list_directory(
                self.path,
                limit=self.limit,
                cancel_event=self._cancel_event,
            )
        except Exception as exc:
            result = {
                "path": self.path,
                "entries": [],
                "errors": [],
                "truncated": False,
                "limit": self.limit,
                "cancelled": False,
                "error": {
                    "path": self.path,
                    "error": str(exc),
                    "kind": "os",
                },
            }
        result["generation"] = self.generation
        self.finished.emit(result)


class _DirectoryThread(QThread):
    def __init__(self, worker):
        super().__init__()
        self.worker = worker

    def run(self):
        self.worker.run()


class _InspectionWorker(QObject):
    finished = Signal(dict)

    def __init__(self, generation, path, inspector, parent=None):
        super().__init__(parent)
        self.generation = generation
        self.path = path
        self.inspector = inspector
        self._cancel_event = threading.Event()

    def request_cancel(self):
        self._cancel_event.set()

    def run(self):
        try:
            result = self.inspector.inspect(
                self.path, cancel_event=self._cancel_event
            )
        except Exception as exc:
            result = _error_inspection_result(self.path, exc)
        result["generation"] = self.generation
        self.finished.emit(result)


class _InspectionThread(QThread):
    def __init__(self, worker):
        super().__init__()
        self.worker = worker

    def run(self):
        self.worker.run()


class ExplorerWidget(QWidget):
    """Read-only directory browser embedded in the Storage screen."""

    def __init__(
        self, initial_path=None, browser=None, inspector=None, parent=None
    ):
        super().__init__(parent)
        self.setObjectName("storageExplorer")
        self.setStyleSheet("background-color: transparent;")
        self.browser = browser or DirectoryBrowser()
        self.inspector = inspector or FileInspector()
        self._current_path = None
        self._entries = []
        self._history = []
        self._history_index = -1
        self._generation = 0
        self._thread = None
        self._worker = None
        self._pending = None
        self._active_add_history = False
        self._loading = False
        self._shutting_down = False
        self._inspect_generation = 0
        self._inspect_thread = None
        self._inspect_worker = None
        self._inspect_pending = None
        self._inspect_key = None
        self._is_inspecting = False

        self._build_ui()
        self.destroyed.connect(self._on_destroyed)
        self.navigate_to(
            os.path.abspath(
                os.path.expanduser(initial_path or "~")
            ),
            add_history=False,
        )

    @property
    def current_path(self):
        return self._current_path

    @property
    def is_loading(self):
        return self._loading

    @property
    def is_inspecting(self):
        return self._is_inspecting

    @staticmethod
    def _section_label(text):
        label = QLabel(text)
        label.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #111827; "
            "padding-top: 6px;"
        )
        return label

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QLabel("Explorer")
        header.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #111827;"
        )
        layout.addWidget(header)

        sub = QLabel(
            "Browse directories and inspect entries without changing them."
        )
        sub.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(sub)

        self.read_only_label = QLabel(
            "Read-only: browsing never authorizes cleanup."
        )
        self.read_only_label.setStyleSheet(
            "background-color: #eff6ff; border: 1px solid #bfdbfe; "
            "border-radius: 6px; padding: 7px 10px; color: #1e40af; "
            "font-size: 11px;"
        )
        layout.addWidget(self.read_only_label)

        nav = QHBoxLayout()
        nav.setSpacing(6)
        self.back_button = self._secondary_button("Back")
        self.forward_button = self._secondary_button("Forward")
        self.up_button = self._secondary_button("Up")
        self.refresh_button = self._secondary_button("Refresh")
        nav.addWidget(self.back_button)
        nav.addWidget(self.forward_button)
        nav.addWidget(self.up_button)
        nav.addWidget(self.refresh_button)

        self.path_input = QLineEdit()
        self.path_input.setMinimumWidth(280)
        self.path_input.setPlaceholderText("Enter a directory path")
        nav.addWidget(self.path_input, 1)

        self.go_button = QPushButton("Go")
        self.go_button.setStyleSheet(
            "padding: 7px 14px; border-radius: 6px; "
            "background-color: #2563eb; color: #ffffff; border: none;"
        )
        nav.addWidget(self.go_button)
        layout.addLayout(nav)

        self.location_label = QLabel("Location: —")
        self.location_label.setWordWrap(True)
        self.location_label.setStyleSheet(
            "color: #374151; font-size: 11px;"
        )
        layout.addWidget(self.location_label)

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
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "color: #374151; font-size: 11px;"
        )
        status_row.addWidget(self.status_label, 3)
        layout.addLayout(status_row)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText(
            "Filter entries by name or path"
        )
        self.filter_input.setClearButtonEnabled(True)
        filter_layout.addWidget(self.filter_input, 1)
        self.filter_status_label = QLabel("")
        self.filter_status_label.setStyleSheet(
            "color: #6b7280; font-size: 11px;"
        )
        filter_layout.addWidget(self.filter_status_label)
        layout.addLayout(filter_layout)

        self.record_model = RecordTableModel(
            [
                ColumnSpec(
                    "Name",
                    lambda entry: entry.get("name", ""),
                    lambda entry: (
                        _SORT_TYPE_ORDER.get(entry.get("type"), 99),
                        str(entry.get("name", "")).casefold(),
                    ),
                    lambda entry: entry.get("path", ""),
                ),
                ColumnSpec(
                    "Type",
                    lambda entry: _TYPE_LABELS.get(
                        entry.get("type"), "Other"
                    ),
                    lambda entry: (
                        _SORT_TYPE_ORDER.get(entry.get("type"), 99),
                        str(entry.get("name", "")).casefold(),
                    ),
                ),
                ColumnSpec(
                    "Size",
                    lambda entry: format_size(entry.get("size")),
                    _size_sort_key,
                ),
                ColumnSpec(
                    "Modified",
                    lambda entry: entry.get("modified") or "—",
                    lambda entry: str(entry.get("modified") or ""),
                ),
                ColumnSpec(
                    "Link/Reparse",
                    lambda entry: (
                        "Link"
                        if entry.get("is_link")
                        else (
                            "Reparse point"
                            if entry.get("is_reparse")
                            else ""
                        )
                    ),
                    lambda entry: (
                        "Link"
                        if entry.get("is_link")
                        else (
                            "Reparse point"
                            if entry.get("is_reparse")
                            else ""
                        )
                    ),
                ),
            ],
            [],
            search_fields=("name", "path"),
        )
        self.proxy_model = RecordFilterProxyModel()
        self.proxy_model.setSourceModel(self.record_model)
        self.table = RecordTableView()
        self.table.setModel(self.proxy_model)
        self.table.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        for column in (1, 2, 3, 4):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )
        self.table.setStyleSheet(
            "QTableView { background-color: #ffffff; "
            "border: 1px solid #e5e7eb; border-radius: 8px; "
            "gridline-color: #f3f4f6; } "
            "QHeaderView::section { background-color: #f9fafb; "
            "padding: 8px; border: none; "
            "border-right: 1px solid #e5e7eb; "
            "border-bottom: 1px solid #e5e7eb; font-weight: 600; }"
        )
        self.table.sortByColumn(0, Qt.AscendingOrder)
        layout.addWidget(self.table, 1)
        self.filter_input.textChanged.connect(
            self._on_filter_changed
        )

        details_card = QFrame()
        details_card.setStyleSheet(
            "QFrame { background-color: #ffffff; "
            "border: 1px solid #e5e7eb; border-radius: 8px; } "
            "QLabel { border: none; background: transparent; }"
        )
        details = QFormLayout(details_card)
        details.setContentsMargins(12, 10, 12, 10)
        details.setSpacing(5)
        details_title = QLabel("Selected Entry")
        details_title.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #111827;"
        )
        details.addRow(details_title)
        self.detail_name_label = QLabel("—")
        self.detail_path_label = QLabel("—")
        self.detail_path_label.setWordWrap(True)
        self.detail_path_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self.detail_type_label = QLabel("—")
        self.detail_extension_label = QLabel("—")
        self.detail_size_label = QLabel("—")
        self.detail_classification_label = QLabel("—")
        self.detail_created_label = QLabel("—")
        self.detail_modified_label = QLabel("—")
        self.detail_accessed_label = QLabel("—")
        self.detail_link_label = QLabel("—")
        self.detail_hidden_label = QLabel("—")
        self.detail_readonly_label = QLabel("—")
        self.detail_attributes_label = QLabel("—")
        self.detail_attributes_label.setWordWrap(True)
        self.detail_signature_format_label = QLabel("—")
        self.detail_signature_status_label = QLabel("—")
        self.detail_signature_status_label.setWordWrap(True)
        self.detail_signature_match_label = QLabel("—")
        self.detail_inspection_label = QLabel("—")
        self.detail_inspection_label.setWordWrap(True)

        details.addRow(self._section_label("File Information"))
        details.addRow("Name:", self.detail_name_label)
        details.addRow("Full path:", self.detail_path_label)
        details.addRow("Type:", self.detail_type_label)
        details.addRow("Extension:", self.detail_extension_label)
        details.addRow("Size:", self.detail_size_label)
        details.addRow("Classification:", self.detail_classification_label)

        details.addRow(self._section_label("Filesystem Metadata"))
        details.addRow("Created:", self.detail_created_label)
        details.addRow("Modified:", self.detail_modified_label)
        details.addRow("Accessed:", self.detail_accessed_label)
        details.addRow("Hidden:", self.detail_hidden_label)
        details.addRow("Read-only:", self.detail_readonly_label)
        details.addRow("Attributes:", self.detail_attributes_label)
        details.addRow("Link/Reparse:", self.detail_link_label)

        details.addRow(self._section_label("File Signature"))
        details.addRow("Detected format:", self.detail_signature_format_label)
        details.addRow("Signature status:", self.detail_signature_status_label)
        details.addRow(
            "Extension comparison:", self.detail_signature_match_label
        )
        details.addRow("Inspection:", self.detail_inspection_label)
        layout.addWidget(details_card)

        self.back_button.clicked.connect(self.go_back)
        self.forward_button.clicked.connect(self.go_forward)
        self.up_button.clicked.connect(self.go_up)
        self.refresh_button.clicked.connect(self.refresh)
        self.go_button.clicked.connect(self._go_to_path)
        self.path_input.returnPressed.connect(self._go_to_path)
        self.table.itemSelectionChanged.connect(
            self._on_selection_changed
        )
        self.table.itemDoubleClicked.connect(self._on_double_clicked)
        self._update_nav_buttons()

    @staticmethod
    def _secondary_button(text):
        button = QPushButton(text)
        button.setStyleSheet(
            "padding: 6px 10px; border-radius: 6px; "
            "background-color: #f3f4f6; color: #111827; "
            "border: 1px solid #d1d5db;"
        )
        return button

    def navigate_to(self, path, add_history=True):
        raw = str(path or "").strip()
        if not raw:
            return
        target = os.path.abspath(os.path.expanduser(raw))
        self._generation += 1
        generation = self._generation
        self.path_input.setText(target)
        self._set_loading(True, target)

        if self._thread is not None:
            self._pending = (generation, target, add_history)
            if self._worker is not None:
                self._worker.request_cancel()
            return

        self._start_listing(generation, target, add_history)

    def go_back(self):
        if self._history_index <= 0:
            return
        self._history_index -= 1
        target = self._history[self._history_index]
        self._generation += 1
        generation = self._generation
        self.path_input.setText(target)
        self._set_loading(True, target)
        self._dispatch(generation, target, False)

    def go_forward(self):
        if self._history_index + 1 >= len(self._history):
            return
        self._history_index += 1
        target = self._history[self._history_index]
        self._generation += 1
        generation = self._generation
        self.path_input.setText(target)
        self._set_loading(True, target)
        self._dispatch(generation, target, False)

    def go_up(self):
        if not self._current_path:
            return
        parent = os.path.dirname(self._current_path)
        if parent and parent != self._current_path:
            self.navigate_to(parent)

    def refresh(self):
        if self._current_path:
            self.navigate_to(self._current_path, add_history=False)

    def _go_to_path(self):
        self.navigate_to(self.path_input.text(), add_history=True)

    def _dispatch(self, generation, target, add_history):
        if self._thread is not None:
            self._pending = (generation, target, add_history)
            if self._worker is not None:
                self._worker.request_cancel()
            return
        self._start_listing(generation, target, add_history)

    def _start_listing(self, generation, target, add_history):
        worker = _DirectoryWorker(
            generation,
            target,
            self.browser,
            DEFAULT_LIST_LIMIT,
        )
        thread = _DirectoryThread(worker)
        worker.finished.connect(
            self._on_listing_finished, Qt.QueuedConnection
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
        self._active_add_history = add_history
        thread.start()

    def _set_loading(self, loading, target=None):
        self._loading = bool(loading)
        self.progress_bar.setVisible(self._loading)
        if self._loading:
            self.progress_bar.setRange(0, 0)
            if target:
                self.status_label.setText(f"Loading {target}...")
                self.status_label.setToolTip("")

    def _on_listing_finished(self, result):
        if result.get("generation") != self._generation:
            return
        self._loading = False
        self.progress_bar.setVisible(False)
        if result.get("cancelled"):
            return
        if result.get("error"):
            self._show_error(result)
            return
        self._apply_result(result, self._active_add_history)

    def _show_error(self, result):
        error = result.get("error") or {}
        target = result.get("path") or ""
        reason = error.get("error") or "Unknown error"
        self.status_label.setText(f"Cannot open {target}: {reason}")
        self.status_label.setToolTip(reason)
        if self._current_path:
            self.path_input.setText(self._current_path)
            self.location_label.setText(
                f"Location: {self._current_path}"
            )
            self.location_label.setToolTip(self._current_path)
        else:
            self.path_input.clear()
            self.location_label.setText("Location: no directory loaded")
            self.location_label.setToolTip("")
            self._entries = []
            self.table.setRowCount(0)
            self._reset_details()
        self._update_nav_buttons()

    def _apply_result(self, result, add_history):
        path = result["path"]
        self._current_path = path
        self._entries = result.get("entries", [])
        self.path_input.setText(path)
        self.location_label.setText(f"Location: {path}")
        self.location_label.setToolTip(path)
        self._populate_table(self._entries)
        self._reset_details()
        self._update_history(path, add_history)
        self._update_nav_buttons()

        parts = [f"{len(self._entries)} entries"]
        if result.get("truncated"):
            limit = result.get("limit", DEFAULT_LIST_LIMIT)
            parts.append(f"showing first {limit} entries")
        errors = result.get("errors") or []
        if errors:
            parts.append(f"{len(errors)} entries skipped")
        self.status_label.setText(" | ".join(parts))
        self.status_label.setToolTip("")

    def _update_history(self, path, add_history):
        if add_history:
            if self._history_index + 1 < len(self._history):
                self._history = self._history[
                    : self._history_index + 1
                ]
            if not self._history or self._history[-1] != path:
                self._history.append(path)
            self._history_index = len(self._history) - 1
        elif not self._history:
            self._history = [path]
            self._history_index = 0

    def _update_nav_buttons(self):
        self.back_button.setEnabled(self._history_index > 0)
        self.forward_button.setEnabled(
            self._history_index + 1 < len(self._history)
        )
        parent = (
            os.path.dirname(self._current_path)
            if self._current_path
            else ""
        )
        self.up_button.setEnabled(
            bool(self._current_path)
            and bool(parent)
            and parent != self._current_path
        )

    def _populate_table(self, entries):
        self.record_model.set_records(entries)
        self._entries = self.record_model.record_list
        self._update_filter_status()

    def _on_filter_changed(self, _text):
        self.proxy_model.set_search_text(self.filter_input.text())
        self._update_filter_status()

    def _update_filter_status(self):
        active = bool(self.filter_input.text().strip())
        total = self.record_model.rowCount()
        visible = self.proxy_model.rowCount()
        if not active:
            self.filter_status_label.setText("")
        elif visible == 0:
            self.filter_status_label.setText(
                "No entries match the current filter."
            )
        else:
            self.filter_status_label.setText(
                f"Showing {visible} of {total} entries."
            )

    def _on_selection_changed(self):
        index = self.table.currentIndex()
        entry = self.table.record_for_index(index)
        if entry is not None:
            self._show_details(entry)
        else:
            self._reset_details()

    def _on_double_clicked(self, item):
        if hasattr(item, "isValid") and item.isValid():
            index = item
        else:
            model = self.table.model()
            index = model.index(item.row(), 0) if model is not None else None
        if index is None:
            return
        entry = self.table.record_for_index(index)
        if entry is None:
            return
        if entry["type"] == "directory":
            self.navigate_to(entry["path"])
        elif entry.get("is_link") or entry.get("is_reparse"):
            self.status_label.setText(
                "Links and reparse points are not followed."
            )
        else:
            self.status_label.setText(
                "Read-only: files are not opened by Explorer."
            )

    @staticmethod
    def _entry_key(entry):
        return (
            entry.get("path"),
            entry.get("type"),
            entry.get("size"),
            entry.get("modified"),
        )

    def _show_details(self, entry):
        self.detail_name_label.setText(entry["name"])
        self.detail_path_label.setText(entry["path"])
        self.detail_path_label.setToolTip(entry["path"])
        self.detail_type_label.setText(
            _TYPE_LABELS.get(entry["type"], "Other")
        )
        extension = os.path.splitext(entry["name"])[1].lower()
        self.detail_extension_label.setText(extension or "None")
        self.detail_size_label.setText(_format_size(entry["size"]))
        self.detail_classification_label.setText(
            _TYPE_LABELS.get(entry["type"], "Other")
        )
        self.detail_modified_label.setText(
            entry.get("modified") or "Unknown"
        )
        if entry.get("is_link"):
            link_text = "Link"
        elif entry.get("is_reparse"):
            link_text = "Reparse point"
        else:
            link_text = "No"
        self.detail_link_label.setText(link_text)
        self.detail_hidden_label.setText(
            "Yes" if entry.get("is_hidden") else "No"
        )

        if entry.get("is_link") or entry.get("is_reparse"):
            self._cancel_inspection()
            self._show_uninspected_details()
            return

        key = self._entry_key(entry)
        if key == self._inspect_key:
            return

        self._set_inspection_loading()
        self._start_inspection(entry)

    def _show_uninspected_details(self):
        for label in (
            self.detail_created_label,
            self.detail_accessed_label,
            self.detail_readonly_label,
            self.detail_attributes_label,
            self.detail_signature_format_label,
            self.detail_signature_status_label,
        ):
            label.setText("Not inspected")
        self.detail_signature_match_label.setText("Not applicable")
        self.detail_inspection_label.setText(
            "Not inspected: links and reparse points are not followed."
        )

    def _set_inspection_loading(self):
        for label in (
            self.detail_created_label,
            self.detail_accessed_label,
            self.detail_readonly_label,
            self.detail_attributes_label,
            self.detail_signature_format_label,
            self.detail_signature_status_label,
            self.detail_signature_match_label,
        ):
            label.setText("Inspecting…")
        self.detail_inspection_label.setText("Inspecting…")

    def _start_inspection(self, entry):
        path = entry.get("path")
        if not path:
            return
        key = self._entry_key(entry)
        if key == self._inspect_key:
            return
        self._inspect_generation += 1
        generation = self._inspect_generation
        self._inspect_key = key
        self._is_inspecting = True
        if self._inspect_thread is not None:
            self._inspect_pending = (generation, path, key)
            if self._inspect_worker is not None:
                self._inspect_worker.request_cancel()
            return
        self._dispatch_inspection(generation, path, key)

    def _dispatch_inspection(self, generation, path, key):
        worker = _InspectionWorker(
            generation, path, self.inspector
        )
        thread = _InspectionThread(worker)
        worker.finished.connect(
            self._on_inspection_finished, Qt.QueuedConnection
        )
        thread.finished.connect(self._on_inspection_thread_finished)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda t=thread: _ACTIVE_THREADS.discard(t)
        )
        _ACTIVE_THREADS.add(thread)
        self._inspect_thread = thread
        self._inspect_worker = worker
        self._inspect_key = key
        self._is_inspecting = True
        thread.start()

    def _cancel_inspection(self):
        self._inspect_generation += 1
        self._inspect_pending = None
        self._inspect_key = None
        if self._inspect_worker is not None:
            self._inspect_worker.request_cancel()
        self._is_inspecting = False

    def _on_inspection_finished(self, result):
        if result.get("generation") != self._inspect_generation:
            return
        self._is_inspecting = False
        if result.get("cancelled"):
            return
        self._apply_inspection(
            result.get("metadata") or {},
            result.get("signature") or {},
        )

    def _on_inspection_thread_finished(self):
        thread = self.sender()
        if thread is not self._inspect_thread:
            return
        self._inspect_thread = None
        self._inspect_worker = None
        if self._shutting_down:
            self._is_inspecting = False
            return
        if self._inspect_pending is not None:
            generation, path, key = self._inspect_pending
            self._inspect_pending = None
            self._dispatch_inspection(generation, path, key)
        else:
            self._is_inspecting = False

    def _apply_inspection(self, metadata, signature):
        if metadata.get("ok"):
            self.detail_type_label.setText(
                _TYPE_LABELS.get(metadata.get("entry_type"), "Other")
            )
            self.detail_extension_label.setText(
                metadata.get("extension") or "None"
            )
            self.detail_size_label.setText(
                _format_size(metadata.get("size"))
            )
            self.detail_classification_label.setText(
                metadata.get("classification") or "Unknown"
            )
            self.detail_created_label.setText(
                metadata.get("created") or "Not available"
            )
            self.detail_modified_label.setText(
                metadata.get("modified") or "Not available"
            )
            self.detail_accessed_label.setText(
                metadata.get("accessed") or "Not available"
            )
            self.detail_readonly_label.setText(
                "Yes" if metadata.get("is_read_only") else "No"
            )
            if metadata.get("attributes_supported"):
                attributes = metadata.get("attributes") or []
                self.detail_attributes_label.setText(
                    ", ".join(attributes) if attributes else "None"
                )
            else:
                self.detail_attributes_label.setText("Not available")
            self.detail_hidden_label.setText(
                "Yes" if metadata.get("is_hidden") else "No"
            )
            if metadata.get("is_link"):
                link_text = "Link"
            elif metadata.get("is_reparse"):
                link_text = "Reparse point"
            else:
                link_text = "No"
            self.detail_link_label.setText(link_text)
            self.detail_inspection_label.setText("Inspection complete.")
        else:
            reason = metadata.get("error") or "Unknown error"
            self.detail_created_label.setText("Not available")
            self.detail_accessed_label.setText("Not available")
            self.detail_readonly_label.setText("Not available")
            self.detail_attributes_label.setText("Not available")
            self.detail_modified_label.setText(
                metadata.get("modified") or "Not available"
            )
            self.detail_inspection_label.setText(
                f"Metadata unavailable: {reason}"
            )

        self._apply_signature(signature)

    def _apply_signature(self, signature):
        status = str(signature.get("status") or "unavailable")
        error = signature.get("error") or "Unknown error"
        if signature.get("no_follow_supported", True):
            self.detail_signature_status_label.setToolTip("")
        else:
            self.detail_signature_status_label.setToolTip(
                "Safe no-follow opening is unavailable on this platform; "
                "links are rejected before any bytes are read."
            )
        if status == "recognized":
            self.detail_signature_format_label.setText(
                signature.get("format_label")
                or signature.get("format")
                or "Unknown"
            )
            self.detail_signature_status_label.setText("Recognized")
            self.detail_signature_match_label.setText(
                _match_label(signature.get("extension_match"))
            )
        elif status == "unknown":
            self.detail_signature_format_label.setText("Unknown")
            self.detail_signature_status_label.setText("Unknown signature")
            self.detail_signature_match_label.setText("No conclusion")
        elif status == "empty":
            self.detail_signature_format_label.setText("None")
            self.detail_signature_status_label.setText("Empty file")
            self.detail_signature_match_label.setText("No conclusion")
        elif status == "unreadable":
            self.detail_signature_format_label.setText("Not available")
            self.detail_signature_status_label.setText(
                f"Unreadable: {error}"
            )
            self.detail_signature_match_label.setText("No conclusion")
        elif status == "changed":
            self.detail_signature_format_label.setText("Not available")
            self.detail_signature_status_label.setText(
                "File changed during inspection"
            )
            self.detail_signature_match_label.setText("No conclusion")
        elif status == "unsupported":
            self.detail_signature_format_label.setText(
                "Not applicable"
            )
            self.detail_signature_status_label.setText(
                "Unsupported entry type"
            )
            self.detail_signature_match_label.setText("Not applicable")
        else:
            self.detail_signature_format_label.setText("Not available")
            self.detail_signature_status_label.setText(
                "Inspection unavailable"
            )
            self.detail_signature_match_label.setText("No conclusion")

    def _reset_details(self):
        self._cancel_inspection()
        for label in (
            self.detail_name_label,
            self.detail_path_label,
            self.detail_type_label,
            self.detail_extension_label,
            self.detail_size_label,
            self.detail_classification_label,
            self.detail_created_label,
            self.detail_modified_label,
            self.detail_accessed_label,
            self.detail_link_label,
            self.detail_hidden_label,
            self.detail_readonly_label,
            self.detail_attributes_label,
            self.detail_signature_format_label,
            self.detail_signature_status_label,
            self.detail_signature_match_label,
            self.detail_inspection_label,
        ):
            label.setText("—")
        self.detail_path_label.setToolTip("")

    def _on_thread_finished(self):
        thread = self.sender()
        if thread is not self._thread:
            return
        self._thread = None
        self._worker = None
        if self._shutting_down:
            self._loading = False
            self.progress_bar.setVisible(False)
            return
        if self._pending is not None:
            generation, target, add_history = self._pending
            self._pending = None
            self._start_listing(generation, target, add_history)

    def shutdown(self, timeout_ms=1000):
        listing_stopped = self._stop_worker(timeout_ms)
        inspection_stopped = self._stop_inspection_worker(timeout_ms)
        if listing_stopped:
            self._loading = False
            self.progress_bar.setVisible(False)
        if inspection_stopped:
            self._is_inspecting = False
        return listing_stopped and inspection_stopped

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

    def _stop_inspection_worker(self, timeout_ms=1000):
        self._inspect_pending = None
        self._inspect_generation += 1
        if self._inspect_worker is not None:
            self._inspect_worker.request_cancel()
        thread = self._inspect_thread
        if thread is None:
            return True
        if not thread.wait(timeout_ms):
            return False
        self._inspect_thread = None
        self._inspect_worker = None
        self._is_inspecting = False
        return True

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    def _on_destroyed(self, *_args):
        self._stop_worker(timeout_ms=1000)
        self._stop_inspection_worker(timeout_ms=1000)
