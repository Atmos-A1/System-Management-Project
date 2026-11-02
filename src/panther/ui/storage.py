"""Storage screen - comprehensive file management.

Shows disk usage, file browser, largest files, duplicate detection,
and safe cleanup capabilities.
"""

import os
import psutil
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, 
    QHeaderView, QTabWidget, QPushButton, QHBoxLayout, QTreeView,
    QFileSystemModel, QSplitter, QTextEdit, QMessageBox, QProgressBar,
    QListWidget, QListWidgetItem, QLineEdit
)
from PySide6.QtCore import QTimer, Qt, QDir

from ..config import config
from ..services.file_scanner import file_scanner
from ..services.duplicate_detector import duplicate_detector
from ..services.cleanup_manager import cleanup_manager


class StorageScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("storageScreen")
        layout = QVBoxLayout(self)

        title = QLabel("Storage Management")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        self.tabs = QTabWidget()
        
        # Tab 1: Disk Overview
        self.disk_tab = self.create_disk_tab()
        self.tabs.addTab(self.disk_tab, "Disk Overview")
        
        # Tab 2: Largest Files
        self.largest_tab = self.create_largest_tab()
        self.tabs.addTab(self.largest_tab, "Largest Files")
        
        # Tab 3: Duplicate Finder
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
        layout = QVBoxLayout(widget)
        
        label = QLabel("Volume Usage")
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)
        
        self.disk_table = QTableWidget(0, 4)
        self.disk_table.setHorizontalHeaderLabels(["Drive", "Total", "Used", "Free"])
        self.disk_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.disk_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.disk_table)
        
        return widget

    def create_largest_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Scan Path:"))
        self.scan_path_input = QLineEdit()
        self.scan_path_input.setText(os.path.expanduser("~\\Downloads"))
        top_layout.addWidget(self.scan_path_input)
        self.scan_largest_btn = QPushButton("Scan")
        self.scan_largest_btn.clicked.connect(self.scan_largest_files)
        top_layout.addWidget(self.scan_largest_btn)
        layout.addLayout(top_layout)
        
        quick_layout = QHBoxLayout()
        quick_layout.addWidget(QLabel("Quick Scan:"))
        for name, path in [
            ("Downloads", os.path.expanduser("~\\Downloads")),
            ("Desktop", os.path.expanduser("~\\Desktop")),
            ("Documents", os.path.expanduser("~\\Documents")),
            ("Pictures", os.path.expanduser("~\\Pictures")),
            ("C:\\Users", "C:\\Users"),
        ]:
            btn = QPushButton(name)
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
        layout.addWidget(self.largest_table)
        
        bottom_layout = QHBoxLayout()
        self.delete_largest_btn = QPushButton("Move Selected to Recycle Bin")
        self.delete_largest_btn.clicked.connect(self.delete_selected_largest)
        bottom_layout.addWidget(self.delete_largest_btn)
        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)
        
        self.scan_progress = QProgressBar()
        self.scan_progress.setVisible(False)
        layout.addWidget(self.scan_progress)
        
        self.largest_files_data = []
        
        return widget

    def create_duplicates_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Scan Path:"))
        self.dup_scan_path = QLineEdit()
        self.dup_scan_path.setText(os.path.expanduser("~\\Downloads"))
        top_layout.addWidget(self.dup_scan_path)
        self.scan_dups_btn = QPushButton("Find Duplicates")
        self.scan_dups_btn.clicked.connect(self.scan_duplicates)
        top_layout.addWidget(self.scan_dups_btn)
        layout.addLayout(top_layout)
        
        quick_layout = QHBoxLayout()
        quick_layout.addWidget(QLabel("Quick Scan:"))
        for name, path in [
            ("Downloads", os.path.expanduser("~\\Downloads")),
            ("Desktop", os.path.expanduser("~\\Desktop")),
            ("Documents", os.path.expanduser("~\\Documents")),
            ("Pictures", os.path.expanduser("~\\Pictures")),
        ]:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, p=path: self.dup_scan_path.setText(p))
            quick_layout.addWidget(btn)
        quick_layout.addStretch()
        layout.addLayout(quick_layout)
        
        info_label = QLabel("Duplicates are found by content hash (SHA256). Files shown have identical content. Scanning depth limited for performance.")
        info_label.setStyleSheet("color: #666;")
        layout.addWidget(info_label)
        
        self.dups_list = QListWidget()
        layout.addWidget(self.dups_list)
        
        bottom_layout = QHBoxLayout()
        self.remove_dups_btn = QPushButton("Move Selected to Recycle Bin")
        self.remove_dups_btn.clicked.connect(self.remove_duplicates)
        bottom_layout.addWidget(self.remove_dups_btn)
        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)
        
        self.dup_progress = QProgressBar()
        self.dup_progress.setVisible(False)
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

    def scan_largest_files(self):
        path = self.scan_path_input.text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Error", "Path does not exist")
            return
        
        self.scan_progress.setVisible(True)
        self.scan_progress.setRange(0, 0)  # Indeterminate
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
            f"Files will be moved to Recycle Bin (reversible).\n\n"
            f"Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        result = cleanup_manager.move_to_recycle_bin(to_remove)
        if result['success']:
            QMessageBox.information(
                self, "Success",
                f"Moved {result['moved']} file(s) to Recycle Bin\n"
                f"Failed: {result['failed']}"
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
                    f"Potential savings: {self._fmt(dup_group['potential_savings'])}"
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
        files = dup_group['files']
        if len(files) < 2:
            return
        
        # Keep first file, move rest to recycle bin
        to_remove = [f['path'] for f in files[1:]]
        
        reply = QMessageBox.warning(
            self, "Confirm Cleanup",
            f"This will move {len(to_remove)} file(s) to the Recycle Bin.\n\n"
            f"Keeping: {files[0]['path']}\n"
            f"Removing: {len(to_remove)} duplicate(s)\n"
            f"Space to free: {self._fmt(dup_group['potential_savings'])}\n\n"
            f"Files will be moved to Recycle Bin (reversible). Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        result = cleanup_manager.move_to_recycle_bin(to_remove)
        if result['success']:
            QMessageBox.information(
                self, "Success",
                f"Moved {result['moved']} file(s) to Recycle Bin\n"
                f"Failed: {result['failed']}"
            )
            # Refresh duplicates
            self.scan_duplicates()
        else:
            QMessageBox.critical(self, "Error", result.get('error', 'Cleanup failed'))
