"""Storage screen - comprehensive file management.

Shows disk usage, file browser, largest files, duplicate detection,
and safe cleanup capabilities.
"""

import os
import psutil
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, 
    QHeaderView, QTabWidget, QPushButton, QHBoxLayout, QLineEdit,
    QMessageBox, QProgressBar, QListWidget, QListWidgetItem
)
from PySide6.QtCore import QTimer, Qt

from ..config import config
from ..services.file_scanner import file_scanner
from ..services.duplicate_detector import duplicate_detector
from ..services.cleanup_manager import cleanup_manager


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
        
        self.disk_tab = self.create_disk_tab()
        self.tabs.addTab(self.disk_tab, "Disk Overview")
        
        self.largest_tab = self.create_largest_tab()
        self.tabs.addTab(self.largest_tab, "Largest Files")
        
        self.duplicates_tab = self.create_duplicates_tab()
        self.tabs.addTab(self.duplicates_tab, "Duplicates")
        
        layout.addWidget(self.tabs)

        self.timer = QTimer(self)
        self.timer.setInterval(config.refresh_interval_seconds * 1000)
        self.timer.timeout.connect(self.refresh_disk)
        self.timer.start()
        self.refresh_disk()

    def create_disk_tab(self):
        widget = QWidget()
        widget.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
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
        
        self.largest_table = QTableWidget(0, 4)
        self.largest_table.setHorizontalHeaderLabels(["Name", "Path", "Size", "Modified"])
        self.largest_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.largest_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.largest_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.largest_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.largest_table.setAlternatingRowColors(True)
        self.largest_table.setStyleSheet("""
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
        layout.addWidget(self.largest_table)
        
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
        
        self.dups_list = QListWidget()
        self.dups_list.setStyleSheet("""
            QListWidget {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #f3f4f6;
            }
            QListWidget::item:selected {
                background-color: #dbeafe;
                color: #111827;
            }
        """)
        layout.addWidget(self.dups_list)
        
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)
        self.remove_dups_btn = QPushButton("Move Selected to Recycle Bin")
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

    def scan_largest_files(self):
        path = self.scan_path_input.text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Error", "Path does not exist")
            return
        
        self.scan_progress.setVisible(True)
        self.scan_progress.setRange(0, 0)
        self.scan_largest_btn.setEnabled(False)
        
        try:
            files = file_scanner.scan_directory(path, max_depth=8)
            largest = file_scanner.get_largest_files(files, 200)
            self.largest_files_data = largest
            
            self.largest_table.setRowCount(len(largest))
            for row, f in enumerate(largest):
                self.largest_table.setItem(row, 0, QTableWidgetItem(f['name']))
                self.largest_table.setItem(row, 1, QTableWidgetItem(f['path']))
                self.largest_table.setItem(row, 2, QTableWidgetItem(self._fmt(f['size'])))
                self.largest_table.setItem(row, 3, QTableWidgetItem(f['modified']))
            self.largest_table.resizeColumnsToContents()
            QMessageBox.information(self, "Scan Complete", f"Found {len(files)} files, showing top {len(largest)} largest")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        finally:
            self.scan_progress.setVisible(False)
            self.scan_largest_btn.setEnabled(True)

    def delete_selected_largest(self):
        selected_rows = set()
        for item in self.largest_table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Select files to delete")
            return
        
        to_remove = []
        total_size = 0
        for row in selected_rows:
            if row < len(self.largest_files_data):
                f = self.largest_files_data[row]
                to_remove.append(f['path'])
                total_size += f['size']
        
        if not to_remove:
            return
        
        reply = QMessageBox.warning(
            self, "Confirm Deletion",
            f"This will move {len(to_remove)} file(s) to the Recycle Bin.\n\n"
            f"Total size: {self._fmt(total_size)}\n\n"
            f"Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        result = cleanup_manager.move_to_recycle_bin(to_remove)
        if result.get('success') or result.get('moved', 0) > 0:
            QMessageBox.information(
                self, "Success",
                f"Moved {result.get('moved', len(to_remove))} file(s) to Recycle Bin\n"
                f"Failed: {result.get('failed', 0)}"
            )
            self.scan_largest_files()
        else:
            QMessageBox.critical(self, "Error", result.get('error', 'Cleanup failed'))

    def scan_duplicates(self):
        path = self.dup_scan_path.text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Error", "Path does not exist")
            return
        
        reply = QMessageBox.question(
            self, "Confirm Scan",
            "Duplicate scanning can take a while for large directories. Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        self.dup_progress.setVisible(True)
        self.dup_progress.setRange(0, 0)
        self.scan_dups_btn.setEnabled(False)
        self.dups_list.clear()
        
        try:
            files = file_scanner.scan_directory(path, max_depth=6)
            duplicates = duplicate_detector.find_duplicates(files)
            
            for dup_group in duplicates:
                item = QListWidgetItem(
                    f"Size: {self._fmt(dup_group['size'])} | {dup_group['count']} copies | "
                    f"Savings: {self._fmt(dup_group['potential_savings'])}"
                )
                item.setData(Qt.UserRole, dup_group)
                self.dups_list.addItem(item)
            
            if not duplicates:
                QMessageBox.information(self, "Scan Complete", "No duplicates found")
            else:
                QMessageBox.information(self, "Scan Complete", f"Found {len(duplicates)} duplicate groups")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        finally:
            self.dup_progress.setVisible(False)
            self.scan_dups_btn.setEnabled(True)

    def remove_duplicates(self):
        current = self.dups_list.currentItem()
        if not current:
            QMessageBox.warning(self, "No Selection", "Select a duplicate group first")
            return
        
        dup_group = current.data(Qt.UserRole)
        files = dup_group.get('files', [])
        if len(files) < 2:
            return
        
        to_remove = [f['path'] for f in files[1:]]
        
        reply = QMessageBox.warning(
            self, "Confirm Cleanup",
            f"This will move {len(to_remove)} file(s) to the Recycle Bin.\n\n"
            f"Keeping: {files[0]['path']}\n"
            f"Removing: {len(to_remove)} duplicate(s)\n"
            f"Space to free: {self._fmt(dup_group['potential_savings'])}\n\n"
            f"Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        result = cleanup_manager.move_to_recycle_bin(to_remove)
        if result.get('success') or result.get('moved', 0) > 0:
            QMessageBox.information(
                self, "Success",
                f"Moved {result.get('moved', len(to_remove))} file(s) to Recycle Bin\n"
                f"Failed: {result.get('failed', 0)}"
            )
            self.scan_duplicates()
        else:
            QMessageBox.critical(self, "Error", result.get('error', 'Cleanup failed'))
