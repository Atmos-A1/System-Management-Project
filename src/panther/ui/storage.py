"""Storage screen - comprehensive file management.

Shows disk usage, file browser, largest files, duplicate detection,
and safe cleanup capabilities.
"""

import os
from collections.abc import Mapping
from datetime import datetime

import psutil
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QWidget, QVBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QPushButton,
    QHBoxLayout, QLineEdit, QMessageBox, QProgressBar, QDialog
)
from PySide6.QtCore import QDate, QTimer, Qt

from ..config import config
from ..services import storage_history
from ..services.cleanup_manager import cleanup_manager
from ..services.cleanup_policy import is_valid_identity
from .cleanup_review import CleanupResultDialog, CleanupReviewDialog
from .duplicate_review import DuplicateReviewWidget
from .explorer import ExplorerWidget
from .insights import InsightsWidget
from .scan_controller import ScanController
from .table_models import (
    ColumnSpec,
    RecordFilterProxyModel,
    RecordTableModel,
    RecordTableView,
    format_size,
)


class StorageScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("storageScreen")
        self.setStyleSheet("""
            QWidget {
                background-color: #f7f9fc;
            }
            QTabWidget::pane {
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                background-color: #ffffff;
            }
            QTabBar::tab {
                background-color: #f3f4f6;
                padding: 8px 16px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                color: #374151;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #111827;
                border: 1px solid #e5e7eb;
                border-bottom: none;
            }
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                gridline-color: #f3f4f6;
                selection-background-color: #dbeafe;
            }
            QHeaderView::section {
                background-color: #f9fafb;
                padding: 6px;
                border: none;
                border-right: 1px solid #e5e7eb;
                border-bottom: 1px solid #e5e7eb;
                font-weight: 600;
            }
            QLineEdit {
                padding: 6px 8px;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                background-color: #ffffff;
            }
            QPushButton {
                padding: 7px 12px;
                border-radius: 6px;
                background-color: #2563eb;
                color: #ffffff;
                border: none;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
            QListWidget {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f3f4f6;
            }
            QListWidget::item:selected {
                background-color: #dbeafe;
                color: #111827;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Storage Management")
        title.setStyleSheet("font-size: 24px; font-weight: 700; color: #111827;")
        layout.addWidget(title)
        
        subtitle = QLabel("Analyze disk usage, find large files and duplicates, clean up safely")
        subtitle.setStyleSheet("font-size: 12px; color: #6b7280;")
        layout.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        
        self.overview_tab = self.create_overview_tab()
        self.disk_tab = self.overview_tab
        self.tabs.addTab(self.overview_tab, "Overview")
        
        self.largest_tab = self.create_largest_tab()
        self.tabs.addTab(self.largest_tab, "Largest Files")
        
        self.duplicates_tab = self.create_duplicates_tab()
        self.tabs.addTab(self.duplicates_tab, "Duplicates")

        self.explorer_tab = self.create_explorer_tab()
        self.tabs.addTab(self.explorer_tab, "Explorer")

        self.insights_tab = self.create_insights_tab()
        self.tabs.addTab(self.insights_tab, "Insights")

        self.scan_history_tab = self.create_scan_history_tab()
        self.tabs.addTab(self.scan_history_tab, "Scan History")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
        layout.addWidget(self.tabs)

        status_bar = QHBoxLayout()
        status_bar.setSpacing(10)
        self.scan_progress_bar = QProgressBar()
        self.scan_progress_bar.setFixedHeight(6)
        self.scan_progress_bar.setTextVisible(False)
        self.scan_progress_bar.setStyleSheet("""
            QProgressBar { border: none; background-color: #f1f5f9; border-radius: 3px; }
            QProgressBar::chunk { background-color: #2563eb; border-radius: 3px; }
        """)
        self.scan_progress_bar.setVisible(False)
        status_bar.addWidget(self.scan_progress_bar, 1)

        self.scan_status_label = QLabel("")
        self.scan_status_label.setStyleSheet("color: #374151; font-size: 12px;")
        status_bar.addWidget(self.scan_status_label, 3)

        self.scan_path_label = QLabel("")
        self.scan_path_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        self.scan_path_label.setMinimumWidth(220)
        status_bar.addWidget(self.scan_path_label, 2)

        self.cancel_scan_btn = QPushButton("Cancel")
        self.cancel_scan_btn.setEnabled(False)
        self.cancel_scan_btn.setVisible(False)
        self.cancel_scan_btn.setStyleSheet(
            "padding: 6px 12px; border-radius: 6px; background-color: #f3f4f6; "
            "color: #111827; border: 1px solid #d1d5db;"
        )
        status_bar.addWidget(self.cancel_scan_btn)
        layout.addLayout(status_bar)

        self._scan_roots = {"largest": None, "duplicates": None}
        self._scanning = False
        self._current_scan_kind = None
        self.scan_controller = ScanController(self)
        self.scan_controller.started.connect(self._on_scan_started)
        self.scan_controller.progress.connect(self._on_scan_progress)
        self.scan_controller.finished.connect(self._on_scan_finished)
        self.scan_controller.cancelled.connect(self._on_scan_cancelled)
        self.scan_controller.failed.connect(self._on_scan_failed)
        self.scan_controller.state_changed.connect(
            self._on_scan_state_changed
        )
        self.cancel_scan_btn.clicked.connect(self.scan_controller.cancel)
        self.destroyed.connect(self._on_screen_destroyed)

        self.timer = QTimer(self)
        self.timer.setInterval(config.refresh_interval_seconds * 1000)
        self.timer.timeout.connect(self.refresh_disk)
        self.timer.start()
        self.refresh_disk()
        self._update_cleanup_availability()
        self._refresh_scan_history()

    def create_overview_tab(self):
        widget = QWidget()
        widget.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        header = QLabel("Storage Overview")
        header.setStyleSheet("font-size: 16px; font-weight: 700; color: #111827;")
        layout.addWidget(header)
        sub = QLabel("Scan activity and available storage volumes")
        sub.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(sub)

        summary_header = QLabel("Scan Summary")
        summary_header.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #111827;"
        )
        layout.addWidget(summary_header)

        self.current_scan_label = QLabel(
            "Current scan: No scan is running."
        )
        self.current_scan_label.setObjectName("overviewCurrentScan")
        self.current_scan_label.setWordWrap(True)
        self.current_scan_label.setStyleSheet(
            "background-color: #ffffff; border: 1px solid #e5e7eb; "
            "border-radius: 6px; padding: 8px; color: #374151; "
            "font-size: 12px;"
        )
        layout.addWidget(self.current_scan_label)

        self.recent_scan_label = QLabel(
            "Recent scan: No completed scan yet."
        )
        self.recent_scan_label.setObjectName("overviewRecentScan")
        self.recent_scan_label.setWordWrap(True)
        self.recent_scan_label.setStyleSheet(
            "background-color: #ffffff; border: 1px solid #e5e7eb; "
            "border-radius: 6px; padding: 8px; color: #374151; "
            "font-size: 12px;"
        )
        layout.addWidget(self.recent_scan_label)

        header = QLabel("Volume Usage")
        header.setStyleSheet("font-size: 16px; font-weight: 700; color: #111827;")
        layout.addWidget(header)
        sub = QLabel("Available drives and space utilization")
        sub.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(sub)
        
        self.disk_table = QTableWidget(0, 4)
        self.disk_table.setHorizontalHeaderLabels(["Drive", "Total", "Used", "Free"])
        self.disk_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.disk_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.disk_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.disk_table.setAlternatingRowColors(True)
        self.disk_table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                gridline-color: #f3f4f6;
            }
            QHeaderView::section {
                background-color: #f9fafb;
                padding: 8px;
                border: none;
                border-right: 1px solid #e5e7eb;
                border-bottom: 1px solid #e5e7eb;
                font-weight: 600;
            }
        """)
        layout.addWidget(self.disk_table)
        
        return widget

    def create_largest_tab(self):
        widget = QWidget()
        widget.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        header = QLabel("Largest Files")
        header.setStyleSheet("font-size: 16px; font-weight: 700; color: #111827;")
        layout.addWidget(header)
        sub = QLabel("Scan directories and move large files to Recycle Bin safely")
        sub.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(sub)
        
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)
        path_label = QLabel("Scan Path:")
        path_label.setStyleSheet("color: #374151;")
        top_layout.addWidget(path_label)
        self.scan_path_input = QLineEdit()
        self.scan_path_input.setText(os.path.expanduser("~\\Downloads"))
        self.scan_path_input.setMinimumWidth(280)
        top_layout.addWidget(self.scan_path_input)
        self.scan_largest_btn = QPushButton("Scan")
        self.scan_largest_btn.clicked.connect(self.scan_largest_files)
        self.scan_largest_btn.setStyleSheet("padding: 7px 14px; border-radius: 6px; background-color: #2563eb; color: #ffffff; border: none;")
        top_layout.addWidget(self.scan_largest_btn)
        layout.addLayout(top_layout)
        
        quick_layout = QHBoxLayout()
        quick_layout.setSpacing(6)
        quick_label = QLabel("Quick Scan:")
        quick_label.setStyleSheet("color: #374151;")
        quick_layout.addWidget(quick_label)
        for name, path in [
            ("Downloads", os.path.expanduser("~\\Downloads")),
            ("Desktop", os.path.expanduser("~\\Desktop")),
            ("Documents", os.path.expanduser("~\\Documents")),
            ("Pictures", os.path.expanduser("~\\Pictures")),
        ]:
            btn = QPushButton(name)
            btn.setStyleSheet("padding: 6px 10px; border-radius: 6px; background-color: #f3f4f6; color: #111827; border: 1px solid #d1d5db;")
            btn.clicked.connect(lambda checked, p=path: self.scan_path_input.setText(p))
            quick_layout.addWidget(btn)
        quick_layout.addStretch()
        layout.addLayout(quick_layout)
        
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)
        self.largest_filter_input = QLineEdit()
        self.largest_filter_input.setPlaceholderText(
            "Filter largest files by name or path"
        )
        self.largest_filter_input.setClearButtonEnabled(True)
        filter_layout.addWidget(self.largest_filter_input, 1)
        self.largest_filter_status = QLabel("")
        self.largest_filter_status.setStyleSheet(
            "color: #6b7280; font-size: 11px;"
        )
        filter_layout.addWidget(self.largest_filter_status)
        layout.addLayout(filter_layout)

        self.largest_model = RecordTableModel(
            [
                ColumnSpec(
                    "Name",
                    lambda item: item.get("name", ""),
                    lambda item: str(item.get("name", "")).casefold(),
                    lambda item: item.get("path", ""),
                ),
                ColumnSpec(
                    "Path",
                    lambda item: item.get("path", ""),
                    lambda item: str(item.get("path", "")).casefold(),
                    lambda item: item.get("path", ""),
                ),
                ColumnSpec(
                    "Size",
                    lambda item: format_size(item.get("size")),
                    lambda item: int(item.get("size") or 0),
                ),
                ColumnSpec(
                    "Modified",
                    lambda item: item.get("modified") or "—",
                    lambda item: str(item.get("modified") or ""),
                ),
            ],
            [],
            search_fields=("name", "path"),
        )
        self.largest_proxy = RecordFilterProxyModel()
        self.largest_proxy.setSourceModel(self.largest_model)
        self.largest_table = RecordTableView()
        self.largest_table.setModel(self.largest_proxy)
        self.largest_table.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )
        self.largest_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.largest_table.setStyleSheet("""
            QTableView {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                gridline-color: #f3f4f6;
            }
            QHeaderView::section {
                background-color: #f9fafb;
                padding: 8px;
                border: none;
                border-right: 1px solid #e5e7eb;
                border-bottom: 1px solid #e5e7eb;
                font-weight: 600;
            }
        """)
        self.largest_table.sortByColumn(2, Qt.DescendingOrder)
        layout.addWidget(self.largest_table)
        self.largest_filter_input.textChanged.connect(
            self._on_largest_filter_changed
        )
        
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)
        self.delete_largest_btn = QPushButton("Move Selected to Recycle Bin")
        self.delete_largest_btn.clicked.connect(self.delete_selected_largest)
        self.delete_largest_btn.setStyleSheet("padding: 7px 12px; border-radius: 6px; background-color: #dc2626; color: #ffffff; border: none;")
        bottom_layout.addWidget(self.delete_largest_btn)
        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)
        
        self.scan_progress = QProgressBar()
        self.scan_progress.setVisible(False)
        self.scan_progress.setFixedHeight(6)
        self.scan_progress.setStyleSheet("""
            QProgressBar { border: none; background-color: #f1f5f9; border-radius: 3px; }
            QProgressBar::chunk { background-color: #2563eb; border-radius: 3px; }
        """)
        layout.addWidget(self.scan_progress)
        
        self.largest_files_data = []
        return widget

    def create_duplicates_tab(self):
        widget = QWidget()
        widget.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        header = QLabel("Duplicate Files")
        header.setStyleSheet("font-size: 16px; font-weight: 700; color: #111827;")
        layout.addWidget(header)
        sub = QLabel("Duplicates found by content hash (SHA256). Keep one copy, move others to Recycle Bin.")
        sub.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(sub)
        
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)
        path_label = QLabel("Scan Path:")
        path_label.setStyleSheet("color: #374151;")
        top_layout.addWidget(path_label)
        self.dup_scan_path = QLineEdit()
        self.dup_scan_path.setText(os.path.expanduser("~\\Downloads"))
        self.dup_scan_path.setMinimumWidth(280)
        top_layout.addWidget(self.dup_scan_path)
        self.scan_dups_btn = QPushButton("Find Duplicates")
        self.scan_dups_btn.clicked.connect(self.scan_duplicates)
        self.scan_dups_btn.setStyleSheet("padding: 7px 14px; border-radius: 6px; background-color: #2563eb; color: #ffffff; border: none;")
        top_layout.addWidget(self.scan_dups_btn)
        layout.addLayout(top_layout)
        
        quick_layout = QHBoxLayout()
        quick_layout.setSpacing(6)
        quick_label = QLabel("Quick Scan:")
        quick_label.setStyleSheet("color: #374151;")
        quick_layout.addWidget(quick_label)
        for name, path in [
            ("Downloads", os.path.expanduser("~\\Downloads")),
            ("Desktop", os.path.expanduser("~\\Desktop")),
            ("Documents", os.path.expanduser("~\\Documents")),
            ("Pictures", os.path.expanduser("~\\Pictures")),
        ]:
            btn = QPushButton(name)
            btn.setStyleSheet("padding: 6px 10px; border-radius: 6px; background-color: #f3f4f6; color: #111827; border: 1px solid #d1d5db;")
            btn.clicked.connect(lambda checked, p=path: self.dup_scan_path.setText(p))
            quick_layout.addWidget(btn)
        quick_layout.addStretch()
        layout.addLayout(quick_layout)
        
        self.dups_panel = DuplicateReviewWidget()
        layout.addWidget(self.dups_panel, 1)
        
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)
        self.remove_dups_btn = QPushButton("Review Selected Removals")
        self.remove_dups_btn.clicked.connect(self.remove_duplicates)
        self.remove_dups_btn.setStyleSheet("padding: 7px 12px; border-radius: 6px; background-color: #dc2626; color: #ffffff; border: none;")
        bottom_layout.addWidget(self.remove_dups_btn)
        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)
        
        self.dup_progress = QProgressBar()
        self.dup_progress.setVisible(False)
        self.dup_progress.setFixedHeight(6)
        self.dup_progress.setStyleSheet("""
            QProgressBar { border: none; background-color: #f1f5f9; border-radius: 3px; }
            QProgressBar::chunk { background-color: #2563eb; border-radius: 3px; }
        """)
        layout.addWidget(self.dup_progress)
        
        return widget

    def create_explorer_tab(self):
        self.explorer_panel = ExplorerWidget()
        return self.explorer_panel

    def create_insights_tab(self):
        self.insights_panel = InsightsWidget()
        self.insights_panel.folder_opened.connect(
            self._open_folder_in_explorer
        )
        return self.insights_panel

    def _open_folder_in_explorer(self, path):
        self.tabs.setCurrentWidget(self.explorer_tab)
        self.explorer_panel.navigate_to(path)

    def create_scan_history_tab(self):
        widget = QWidget()
        widget.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        header = QLabel("Scan History")
        header.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #111827;"
        )
        layout.addWidget(header)
        sub = QLabel(
            "Read-only summaries of completed, partial, cancelled and "
            "failed scans. Run a fresh scan before cleaning up files."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(sub)

        self._history_page = 1
        self._history_page_size = storage_history.DEFAULT_PAGE_SIZE
        self._history_total = 0
        self._history_page_count = 0
        self._history_anchor_id = None

        filters = QHBoxLayout()
        filters.setSpacing(6)
        filters.addWidget(QLabel("Type:"))
        self.history_kind_filter = QComboBox()
        self.history_kind_filter.addItem("All types", None)
        self.history_kind_filter.addItem("Largest Files", "largest")
        self.history_kind_filter.addItem("Duplicates", "duplicates")
        self.history_kind_filter.addItem("Analysis", "analysis")
        filters.addWidget(self.history_kind_filter)

        filters.addWidget(QLabel("Status:"))
        self.history_status_filter = QComboBox()
        self.history_status_filter.addItem("All statuses", None)
        self.history_status_filter.addItem("Completed", "completed")
        self.history_status_filter.addItem("Partial", "partial")
        self.history_status_filter.addItem("Cancelled", "cancelled")
        self.history_status_filter.addItem("Failed", "failed")
        filters.addWidget(self.history_status_filter)

        self.history_search_input = QLineEdit()
        self.history_search_input.setPlaceholderText(
            "Search root, type, status, or error"
        )
        self.history_search_input.setClearButtonEnabled(True)
        filters.addWidget(self.history_search_input, 1)

        self.history_clear_filters_button = QPushButton("Clear Filters")
        self.history_clear_filters_button.setStyleSheet(
            "padding: 6px 10px; border-radius: 6px; "
            "background-color: #f3f4f6; color: #111827; "
            "border: 1px solid #d1d5db;"
        )
        filters.addWidget(self.history_clear_filters_button)
        layout.addLayout(filters)

        date_row = QHBoxLayout()
        date_row.setSpacing(6)
        date_row.addWidget(QLabel("Start:"))
        self.history_start_date = QDateEdit()
        self.history_start_date.setCalendarPopup(True)
        self.history_start_date.setDisplayFormat("yyyy-MM-dd")
        self.history_start_date.setMinimumDate(QDate(1900, 1, 1))
        self.history_start_date.setSpecialValueText("Any")
        self.history_start_date.setDate(self.history_start_date.minimumDate())
        date_row.addWidget(self.history_start_date)
        date_row.addWidget(QLabel("End:"))
        self.history_end_date = QDateEdit()
        self.history_end_date.setCalendarPopup(True)
        self.history_end_date.setDisplayFormat("yyyy-MM-dd")
        self.history_end_date.setMinimumDate(QDate(1900, 1, 1))
        self.history_end_date.setSpecialValueText("Any")
        self.history_end_date.setDate(self.history_end_date.minimumDate())
        date_row.addWidget(self.history_end_date)

        date_row.addStretch()
        self.history_prev_button = QPushButton("Previous")
        self.history_next_button = QPushButton("Next")
        for button in (self.history_prev_button, self.history_next_button):
            button.setStyleSheet(
                "padding: 6px 10px; border-radius: 6px; "
                "background-color: #f3f4f6; color: #111827; "
                "border: 1px solid #d1d5db;"
            )
        self.history_prev_button.setEnabled(False)
        self.history_next_button.setEnabled(False)
        date_row.addWidget(self.history_prev_button)
        self.history_page_label = QLabel("Page 1 of 1 | 0 records")
        self.history_page_label.setStyleSheet(
            "color: #374151; font-size: 11px;"
        )
        date_row.addWidget(self.history_page_label)
        date_row.addWidget(self.history_next_button)
        layout.addLayout(date_row)

        self.history_error_label = QLabel("")
        self.history_error_label.setWordWrap(True)
        self.history_error_label.setStyleSheet(
            "color: #b91c1c; font-size: 11px;"
        )
        self.history_error_label.setVisible(False)
        layout.addWidget(self.history_error_label)

        self.history_empty_label = QLabel(
            "No scan history yet. Scan results will appear here."
        )
        self.history_empty_label.setStyleSheet(
            "color: #6b7280; font-size: 12px; padding: 12px;"
        )
        layout.addWidget(self.history_empty_label)

        self.history_model = RecordTableModel(
            [
                ColumnSpec(
                    "Scan Type",
                    lambda record: self._history_kind_label(
                        record.get("kind")
                    ),
                ),
                ColumnSpec(
                    "Root",
                    lambda record: str(
                        record.get("root") or "Unknown"
                    ),
                ),
                ColumnSpec(
                    "Status",
                    lambda record: self._history_status_label(
                        record.get("status")
                    ),
                ),
                ColumnSpec(
                    "Files Scanned",
                    lambda record: str(
                        self._history_int(record.get("files_scanned"))
                    ),
                ),
                ColumnSpec(
                    "Duration",
                    lambda record: self._format_elapsed(
                        record.get("elapsed_seconds")
                    ),
                ),
                ColumnSpec(
                    "Timestamp",
                    lambda record: self._history_timestamp(
                        record.get("timestamp")
                    ),
                ),
                ColumnSpec(
                    "Skipped / Errors",
                    lambda record: str(
                        self._history_int(record.get("skipped_count"))
                    ),
                ),
            ],
            [],
        )
        self.history_table = RecordTableView()
        self.history_table.setModel(self.history_model)
        self.history_table.setSortingEnabled(False)
        self.history_table.setSelectionMode(
            QAbstractItemView.NoSelection
        )
        self.history_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.history_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        for column in (2, 3, 4, 5, 6):
            self.history_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )
        self.history_table.setStyleSheet(
            "QTableView { background-color: #ffffff; "
            "border: 1px solid #e5e7eb; border-radius: 8px; "
            "gridline-color: #f3f4f6; } "
            "QHeaderView::section { background-color: #f9fafb; "
            "padding: 8px; border: none; "
            "border-right: 1px solid #e5e7eb; "
            "border-bottom: 1px solid #e5e7eb; font-weight: 600; }"
        )
        layout.addWidget(self.history_table, 1)

        self.history_kind_filter.currentIndexChanged.connect(
            self._on_history_filters_changed
        )
        self.history_status_filter.currentIndexChanged.connect(
            self._on_history_filters_changed
        )
        self.history_start_date.dateChanged.connect(
            self._on_history_filters_changed
        )
        self.history_end_date.dateChanged.connect(
            self._on_history_filters_changed
        )
        self.history_search_input.textChanged.connect(
            self._on_history_filters_changed
        )
        self.history_clear_filters_button.clicked.connect(
            self._clear_history_filters
        )
        self.history_prev_button.clicked.connect(
            self._history_previous_page
        )
        self.history_next_button.clicked.connect(self._history_next_page)
        return widget

    def _fmt(self, b: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} PB"

    def refresh_disk(self):
        partitions = []
        for p in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(p.mountpoint)
                partitions.append((p.mountpoint, usage))
            except (PermissionError, OSError):
                continue

        self.disk_table.setRowCount(len(partitions))
        for row, (mount, usage) in enumerate(partitions):
            self.disk_table.setItem(row, 0, QTableWidgetItem(mount))
            self.disk_table.setItem(row, 1, QTableWidgetItem(self._fmt(usage.total)))
            self.disk_table.setItem(row, 2, QTableWidgetItem(
                f"{self._fmt(usage.used)} ({usage.percent:.0f}%)"
            ))
            self.disk_table.setItem(row, 3, QTableWidgetItem(self._fmt(usage.free)))
        self.disk_table.resizeColumnsToContents()

    def _on_tab_changed(self, index):
        if self.tabs.widget(index) is self.scan_history_tab:
            self._refresh_scan_history(reset_page=True)

    def _history_date_filter(self, widget):
        if widget.date() == widget.minimumDate():
            return None
        return widget.date().toString("yyyy-MM-dd")

    def _history_filter_values(self):
        return {
            "kind": self.history_kind_filter.currentData(),
            "status": self.history_status_filter.currentData(),
            "start_date": self._history_date_filter(
                self.history_start_date
            ),
            "end_date": self._history_date_filter(self.history_end_date),
            "search": self.history_search_input.text(),
        }

    def _history_filters_active(self):
        values = self._history_filter_values()
        return any(
            values[field]
            for field in ("kind", "status", "start_date", "end_date")
        ) or bool(str(values["search"] or "").strip())

    def _on_history_filters_changed(self, *_args):
        self._refresh_scan_history(reset_page=True)

    def _clear_history_filters(self):
        for widget in (
            self.history_kind_filter,
            self.history_status_filter,
            self.history_start_date,
            self.history_end_date,
            self.history_search_input,
        ):
            widget.blockSignals(True)
        try:
            self.history_kind_filter.setCurrentIndex(0)
            self.history_status_filter.setCurrentIndex(0)
            self.history_start_date.setDate(
                self.history_start_date.minimumDate()
            )
            self.history_end_date.setDate(
                self.history_end_date.minimumDate()
            )
            self.history_search_input.clear()
        finally:
            for widget in (
                self.history_kind_filter,
                self.history_status_filter,
                self.history_start_date,
                self.history_end_date,
                self.history_search_input,
            ):
                widget.blockSignals(False)
        self._refresh_scan_history(reset_page=True)

    def _history_previous_page(self):
        if self._history_page > 1:
            self._history_page -= 1
            self._refresh_scan_history(reset_page=False)

    def _history_next_page(self):
        if self._history_page < self._history_page_count:
            self._history_page += 1
            self._refresh_scan_history(reset_page=False)

    def _set_history_error(self, message):
        self.history_error_label.setText(message)
        self.history_error_label.setVisible(True)

    def _refresh_scan_history(self, reset_page=True):
        if reset_page:
            self._history_page = 1
            self._history_anchor_id = None

        filters = self._history_filter_values()
        self.history_page_label.setText("Loading...")
        try:
            result = storage_history.get_scan_history_page(
                page=self._history_page,
                page_size=self._history_page_size,
                kind=filters["kind"],
                status=filters["status"],
                start_date=filters["start_date"],
                end_date=filters["end_date"],
                search=filters["search"],
                max_id=self._history_anchor_id,
            )
        except ValueError as exc:
            self.history_model.set_records([])
            self._history_page = 1
            self._history_total = 0
            self._history_page_count = 0
            self.history_prev_button.setEnabled(False)
            self.history_next_button.setEnabled(False)
            self.history_page_label.setText("Page 1 of 1 | 0 records")
            self.history_empty_label.setVisible(False)
            self._set_history_error(str(exc))
            return
        except Exception as exc:
            self.history_model.set_records([])
            self._history_page = 1
            self._history_total = 0
            self._history_page_count = 0
            self.history_prev_button.setEnabled(False)
            self.history_next_button.setEnabled(False)
            self.history_page_label.setText("Page 1 of 1 | 0 records")
            self.history_empty_label.setVisible(False)
            self._set_history_error(
                f"Unable to load scan history: {exc}"
            )
            return

        self.history_error_label.clear()
        self.history_error_label.setVisible(False)
        self._history_page = int(result.get("page", 1) or 1)
        self._history_total = int(result.get("total", 0) or 0)
        self._history_page_count = int(
            result.get("page_count", 0) or 0
        )
        self._history_anchor_id = result.get("max_id")

        safe_records = []
        for record in result.get("records", []) or []:
            if not isinstance(record, dict):
                continue
            try:
                self._history_kind_label(record.get("kind"))
                self._history_status_label(record.get("status"))
                self._history_int(record.get("files_scanned"))
                self._format_elapsed(record.get("elapsed_seconds"))
                self._history_timestamp(record.get("timestamp"))
                self._history_int(record.get("skipped_count"))
            except Exception:
                # One malformed record must not hide the remaining history.
                continue
            safe_records.append(record)
        self.history_model.set_records(safe_records)

        self.history_empty_label.setText(
            "No scan history matches the current filters."
            if self._history_filters_active()
            else "No scan history yet. Scan results will appear here."
        )
        self.history_empty_label.setVisible(not safe_records)

        if self._history_total:
            self.history_page_label.setText(
                f"Page {self._history_page} of "
                f"{max(1, self._history_page_count)} | "
                f"{result.get('start_index', 0)}-"
                f"{result.get('end_index', 0)} of "
                f"{self._history_total} records"
            )
        else:
            self.history_page_label.setText(
                "Page 1 of 1 | 0 records"
            )
        self.history_prev_button.setEnabled(
            bool(result.get("has_previous"))
        )
        self.history_next_button.setEnabled(
            bool(result.get("has_next"))
        )

    def _record_scan_history(self, payload, status):
        try:
            storage_history.record_scan(payload, status)
        except Exception:
            # Recording is best-effort; scan results remain authoritative.
            pass
        try:
            self._refresh_scan_history(reset_page=True)
        except Exception:
            pass

    @staticmethod
    def _history_int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError, OverflowError):
            return 0

    @staticmethod
    def _history_kind_label(kind):
        labels = {
            "largest": "Largest Files",
            "duplicates": "Duplicates",
            "analysis": "Analysis",
        }
        return labels.get(str(kind or ""), "Unknown")

    @staticmethod
    def _history_status_label(status):
        value = str(status or "unknown")
        return value.capitalize() if value else "Unknown"

    @staticmethod
    def _history_timestamp(value):
        text = str(value or "").strip()
        if not text:
            return "Unknown"
        try:
            return datetime.fromisoformat(text).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            return text

    def scan_largest_files(self):
        path = self.scan_path_input.text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Error", "Path does not exist")
            return
        if self.scan_controller.is_running:
            self.scan_status_label.setText("A scan is already running.")
            return

        if not self.scan_controller.start("largest", path, max_depth=8):
            self.scan_status_label.setText("A scan is already running.")

    def scan_duplicates(self):
        path = self.dup_scan_path.text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Error", "Path does not exist")
            return
        if self.scan_controller.is_running:
            self.scan_status_label.setText("A scan is already running.")
            return

        reply = QMessageBox.question(
            self, "Confirm Scan",
            "Duplicate scanning can take a while for large directories. Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        if not self.scan_controller.start("duplicates", path, max_depth=6):
            self.scan_status_label.setText("A scan is already running.")

    def _on_scan_started(self, kind):
        self._scan_roots[kind] = None
        self._current_scan_kind = kind
        self.scan_progress_bar.setRange(0, 0)
        self.scan_progress_bar.setVisible(True)
        self.scan_status_label.setText(
            "Scanning for largest files..." if kind == "largest"
            else "Scanning for duplicates..."
        )
        self.current_scan_label.setText(
            f"Current scan: {self._scan_kind_label(kind)} scan in progress."
        )
        path = (
            self.scan_path_input.text()
            if kind == "largest"
            else self.dup_scan_path.text()
        )
        self.scan_path_label.setText(path)
        self.scan_path_label.setToolTip(path)
        self._set_scanning(True)

    def _on_scan_progress(self, payload):
        phase = payload.get("phase")
        elapsed = self._format_elapsed(payload.get("elapsed_seconds", 0.0))
        if phase == "hash":
            total = int(payload.get("total_bytes", 0) or 0)
            hashed = int(payload.get("bytes_hashed", 0) or 0)
            if total > 0:
                self.scan_progress_bar.setRange(0, total)
                self.scan_progress_bar.setValue(min(hashed, total))
            else:
                self.scan_progress_bar.setRange(0, 0)
            status = (
                f"Hashing: {payload.get('files_hashed', 0)}/"
                f"{payload.get('total_files', 0)} files"
                f" | {self._fmt(hashed)} | {elapsed}"
            )
        else:
            self.scan_progress_bar.setRange(0, 0)
            status = (
                f"Scanning: {payload.get('files_scanned', 0)} files"
                f" | {payload.get('directories_scanned', 0)} folders"
                f" | {self._fmt(payload.get('bytes_scanned', 0))}"
                f" | {elapsed}"
            )
        self.scan_status_label.setText(status)
        self.current_scan_label.setText(
            f"Current scan: {self._scan_kind_label(self._current_scan_kind)} "
            f"- {status}"
        )
        current_path = payload.get("current_path", "")
        self.scan_path_label.setText(current_path)
        self.scan_path_label.setToolTip(current_path)

    def _on_scan_finished(self, payload):
        kind = payload.get("kind")
        partial = bool(payload.get("partial"))
        if kind in self._scan_roots:
            self._scan_roots[kind] = (
                None if partial else payload.get("root")
            )
        errors = payload.get("errors", [])
        files_scanned = payload.get("files_scanned", 0)
        elapsed = self._format_elapsed(payload.get("elapsed_seconds", 0.0))

        if kind == "largest":
            self._populate_largest(payload.get("largest", []))
            summary = (
                f"Scan complete: {files_scanned} files scanned, "
                f"showing top {len(self.largest_files_data)} largest."
            )
        else:
            self._populate_duplicates(payload.get("duplicates", []))
            summary = (
                f"Scan complete: {files_scanned} files scanned, "
                f"{self.dups_panel.group_count} duplicate groups."
            )

        if errors:
            summary += f" {len(errors)} item(s) skipped."
        summary += f" Elapsed {elapsed}."
        self.scan_status_label.setText(summary)

        root = payload.get("root")
        recent = f"{self._scan_kind_label(kind)} - {summary}"
        if root:
            recent += f" | Root: {root}"
        self.recent_scan_label.setText(f"Recent scan: {recent}")
        self.recent_scan_label.setToolTip(recent)
        self.current_scan_label.setText("Current scan: No scan is running.")
        self._current_scan_kind = None
        self._update_cleanup_availability()
        self._record_scan_history(
            payload, "partial" if partial else "completed"
        )
        self.scan_path_label.setText("")

    def _on_scan_cancelled(self, payload):
        kind = payload.get("kind") or "scan"
        self.scan_status_label.setText(
            f"{kind.capitalize()} scan cancelled."
        )
        self.current_scan_label.setText(
            f"Current scan: {self._scan_kind_label(kind)} scan cancelled."
        )
        self._current_scan_kind = None
        self._update_cleanup_availability()
        self._record_scan_history(payload, "cancelled")
        self.scan_path_label.setText("")

    def _on_scan_failed(self, payload):
        self.scan_status_label.setText(
            f"Scan failed: {payload.get('error', 'Unknown error')}"
        )
        self.current_scan_label.setText(
            f"Current scan: {self._scan_kind_label(payload.get('kind'))} "
            f"scan failed: {payload.get('error', 'Unknown error')}."
        )
        self._current_scan_kind = None
        self._update_cleanup_availability()
        self._record_scan_history(payload, "failed")
        self.scan_path_label.setText("")

    def _on_scan_state_changed(self, active):
        self._set_scanning(active)

    def _populate_largest(self, largest):
        self.largest_model.set_records(largest or [])
        self.largest_files_data = self.largest_model.record_list
        self._update_largest_filter_status()

    def _on_largest_filter_changed(self, _text):
        self.largest_proxy.set_search_text(
            self.largest_filter_input.text()
        )
        self._update_largest_filter_status()

    def _update_largest_filter_status(self):
        active = bool(self.largest_filter_input.text().strip())
        total = self.largest_model.rowCount()
        visible = self.largest_proxy.rowCount()
        if not active:
            self.largest_filter_status.setText("")
        elif visible == 0:
            self.largest_filter_status.setText(
                "No files match the current filter."
            )
        else:
            self.largest_filter_status.setText(
                f"Showing {visible} of {total} files."
            )

    def _populate_duplicates(self, duplicates):
        self.dups_panel.set_groups(duplicates)

    def _set_scanning(self, active):
        self._scanning = bool(active)
        self.scan_largest_btn.setEnabled(not active)
        self.scan_dups_btn.setEnabled(not active)
        self.scan_path_input.setEnabled(not active)
        self.dup_scan_path.setEnabled(not active)
        self.cancel_scan_btn.setVisible(active)
        self.cancel_scan_btn.setEnabled(active)
        self.scan_progress_bar.setVisible(active)
        self._update_cleanup_availability()

    def _update_cleanup_availability(self):
        self.delete_largest_btn.setEnabled(
            not self._scanning and bool(self._scan_roots.get("largest"))
        )
        self.remove_dups_btn.setEnabled(
            not self._scanning and bool(self._scan_roots.get("duplicates"))
        )

    @staticmethod
    def _scan_kind_label(kind):
        labels = {"largest": "Largest Files", "duplicates": "Duplicates"}
        return labels.get(kind, "Storage")

    def _format_elapsed(self, seconds):
        try:
            total = max(0, int(seconds or 0))
        except (TypeError, ValueError, OverflowError):
            total = 0
        return f"{total // 60:02d}:{total % 60:02d}"

    def _on_screen_destroyed(self, *_args):
        self.scan_controller.shutdown(timeout_ms=1000)

    def closeEvent(self, event):
        if not self.scan_controller.shutdown():
            self.scan_status_label.setText("Stopping scan...")
        super().closeEvent(event)

    def delete_selected_largest(self):
        if self.scan_controller.is_running:
            return
        selected_files = self.largest_table.selected_records()

        if not selected_files:
            QMessageBox.warning(self, "No Selection", "Select files to delete")
            return

        to_remove = [
            item["path"] for item in selected_files if item.get("path")
        ]
        if not to_remove:
            return

        root = self._scan_roots.get("largest")
        preview = self._preview_cleanup(to_remove, root)
        if preview is None:
            return
        reviewed_identities = self._reviewed_identities(preview)
        if reviewed_identities is None:
            QMessageBox.warning(
                self,
                "Cleanup Blocked",
                "The reviewed file identity mapping is unavailable or "
                "invalid. Run the scan again before cleaning up files.",
            )
            return
        sizes = {item["path"]: item["size"] for item in selected_files}
        dialog = CleanupReviewDialog(preview, sizes, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        result = cleanup_manager.move_to_recycle_bin(
            dialog.eligible_paths,
            allowed_roots=[root],
            expected_identities=reviewed_identities,
        )
        CleanupResultDialog(result, self).exec()
        if result.get("moved", 0) > 0:
            self.scan_largest_files()

    def remove_duplicates(self):
        if self.scan_controller.is_running:
            return
        selection = self.dups_panel.current_selection
        if selection is None:
            QMessageBox.warning(
                self, "No Selection", "Select a duplicate group first"
            )
            return

        to_remove = self.dups_panel.removal_paths
        if not to_remove:
            QMessageBox.warning(
                self,
                "No Selection",
                "Select at least one copy to remove.",
            )
            return

        root = self._scan_roots.get("duplicates")
        preview = self._preview_cleanup(to_remove, root)
        if preview is None:
            return
        reviewed_identities = self._reviewed_identities(preview)
        if reviewed_identities is None:
            QMessageBox.warning(
                self,
                "Cleanup Blocked",
                "The reviewed file identity mapping is unavailable or "
                "invalid. Run the scan again before cleaning up files.",
            )
            return
        dialog = CleanupReviewDialog(
            preview, self.dups_panel.removal_sizes, self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        result = cleanup_manager.move_to_recycle_bin(
            dialog.eligible_paths,
            allowed_roots=[root],
            expected_identities=reviewed_identities,
        )
        CleanupResultDialog(result, self).exec()
        if result.get("moved", 0) > 0:
            self.scan_duplicates()

    def _reviewed_identities(self, preview):
        """Return the preview identity mapping to use after confirmation.

        ``None`` means the review cannot be trusted and cleanup must stop.
        Identities are never recaptured here; the mapping shown in the review
        is returned unchanged so execution can compare against it.
        """
        allowed = [str(path) for path in (preview.get("allowed") or [])]
        if not allowed:
            return {}
        identities = preview.get("identities")
        if not isinstance(identities, Mapping):
            return None
        try:
            reviewed = dict(identities)
        except Exception:
            return None
        if any(
            not is_valid_identity(value) for value in reviewed.values()
        ):
            return None
        if any(
            not is_valid_identity(reviewed.get(path)) for path in allowed
        ):
            return None
        return reviewed

    def _preview_cleanup(self, paths, root):
        if not root:
            QMessageBox.warning(
                self,
                "Scan Required",
                "Run a scan before cleaning up files.",
            )
            return None

        return cleanup_manager.preflight_cleanup(paths, [root])

    def _format_cleanup_outcomes(self, result):
        lines = []
        for outcome in result.get("outcomes", []):
            status = outcome.get("status", "failed").capitalize()
            reason = outcome.get("reason", "")
            suffix = f": {reason}" if reason else ""
            lines.append(f"{status}: {outcome.get('path')}{suffix}")
        return "\n".join(lines)
