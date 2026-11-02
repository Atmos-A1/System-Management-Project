"""Process screen - displays running processes with management capabilities.

Shows process list with classification, allows searching/filtering/sorting,
and provides safe termination options with confirmations.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QPushButton, 
    QLineEdit, QLabel, QComboBox, QSplitter, QTextEdit, QMessageBox
)
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex, QTimer, QSortFilterProxyModel

from ..services.process_adapter import get_processes
from ..services.process_classifier import classify_process
from ..services.process_actions import process_action_manager
from ..config import config


class ProcessTableModel(QAbstractTableModel):
    def __init__(self, processes=None):
        super().__init__()
        self.headers = ["PID", "Name", "User", "CPU %", "RAM (MiB)", "Status", "Category", "Executable"]
        self._processes = processes or []
        self._classifications = {}

    def set_processes(self, processes):
        self._processes = processes
        self._classifications = {}
        for p in processes:
            try:
                self._classifications[p.get('pid')] = classify_process(p)
            except Exception:
                self._classifications[p.get('pid')] = {
                    "category": "Unknown / unverified",
                    "can_terminate": False,
                    "risk_level": "Unknown"
                }
        self.layoutChanged.emit()

    def rowCount(self, parent=QModelIndex()):
        return len(self._processes)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        proc = self._processes[index.row()]
        col = index.column()
        pid = proc.get('pid')
        classification = self._classifications.get(pid, {})
        
        if role == Qt.DisplayRole:
            if col == 0:
                return str(proc.get('pid', ''))
            elif col == 1:
                return proc.get('name', '')
            elif col == 2:
                user = proc.get('username') or ''
                return user.split('\\')[-1] if '\\' in user else user
            elif col == 3:
                cpu = proc.get('cpu_percent', 0) or 0
                try:
                    return f"{float(cpu):.1f}"
                except Exception:
                    return "0.0"
            elif col == 4:
                try:
                    return f"{(proc.get('memory_rss', 0) or 0) // (1024**2)}"
                except Exception:
                    return "0"
            elif col == 5:
                return proc.get('status', '')
            elif col == 6:
                return classification.get('category', 'Unknown / unverified')
            elif col == 7:
                exe = proc.get('exe') or ''
                if len(exe) > 60:
                    return '...' + exe[-57:]
                return exe
            return None
        elif role == Qt.ToolTipRole:
            if col == 6:
                return f"Risk: {classification.get('risk_level', 'Unknown')}\n{classification.get('explanation', '')}"
            elif col == 7:
                return proc.get('exe') or ''
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]
        return super().headerData(section, orientation, role)

    def get_process_at(self, row):
        if 0 <= row < len(self._processes):
            return self._processes[row]
        return None


class ProcessesScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("processesScreen")
        self.setStyleSheet("""
            QWidget {
                background-color: #f7f9fc;
            }
            QTableView {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                gridline-color: #f3f4f6;
                selection-background-color: #dbeafe;
                selection-color: #111827;
            }
            QHeaderView::section {
                background-color: #f9fafb;
                padding: 6px;
                border: none;
                border-right: 1px solid #e5e7eb;
                border-bottom: 1px solid #e5e7eb;
                font-weight: 600;
            }
            QLineEdit, QComboBox {
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
            QPushButton:disabled {
                background-color: #9ca3af;
            }
            QTextEdit {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
            }
        """)
        self.all_processes = []
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)
        
        header = QLabel("Processes & RAM Management")
        header.setStyleSheet("font-size: 24px; font-weight: 700; color: #111827;")
        main_layout.addWidget(header)
        
        subtitle = QLabel("Focus on user/app processes affecting RAM. Critical system processes are hidden for safety.")
        subtitle.setStyleSheet("font-size: 12px; color: #6b7280;")
        main_layout.addWidget(subtitle)
        
        # Top bar with search and filters
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search processes by name...")
        self.search_input.setFixedWidth(260)
        self.search_input.textChanged.connect(self.filter_processes)
        top_bar.addWidget(QLabel("Search:"))
        top_bar.addWidget(self.search_input)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All (User)", "User Applications", "High Memory (>100MB)", "High CPU (>10%)"])
        self.filter_combo.currentTextChanged.connect(self.filter_processes)
        top_bar.addWidget(QLabel("Filter:"))
        top_bar.addWidget(self.filter_combo)
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        top_bar.addWidget(self.refresh_btn)
        top_bar.addStretch()
        
        main_layout.addLayout(top_bar)
        
        # Splitter for table and details
        splitter = QSplitter(Qt.Vertical)
        splitter.setStyleSheet("QSplitter::handle { background-color: #e5e7eb; }")
        
        # Table
        table_widget = QWidget()
        table_widget.setStyleSheet("background-color: transparent;")
        table_layout = QVBoxLayout(table_widget)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableView()
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.clicked.connect(self.show_process_details)
        self.model = ProcessTableModel()
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self.table.setModel(self.proxy)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        table_layout.addWidget(self.table)
        splitter.addWidget(table_widget)
        
        # Details panel
        details_widget = QWidget()
        details_widget.setStyleSheet("background-color: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px;")
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(16, 12, 16, 12)
        details_layout.setSpacing(10)
        details_label = QLabel("Process Details & Actions")
        details_label.setStyleSheet("font-weight: 600; font-size: 13px; color: #111827;")
        details_layout.addWidget(details_label)
        
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMinimumHeight(130)
        details_layout.addWidget(self.details_text)
        
        # Action buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        self.close_btn = QPushButton("Close Application (Graceful)")
        self.close_btn.clicked.connect(self.close_selected_process)
        self.force_kill_btn = QPushButton("Force Kill (Advanced)")
        self.force_kill_btn.clicked.connect(self.force_kill_selected_process)
        self.force_kill_btn.setStyleSheet("padding: 7px 12px; border-radius: 6px; background-color: #dc2626; color: #ffffff; border: none;")
        actions_layout.addWidget(self.close_btn)
        actions_layout.addWidget(self.force_kill_btn)
        actions_layout.addStretch()
        details_layout.addLayout(actions_layout)
        
        splitter.addWidget(details_widget)
        splitter.setSizes([420, 160])
        main_layout.addWidget(splitter)
        
        # Timer for auto-refresh
        self.timer = QTimer(self)
        self.timer.setInterval(config.refresh_interval_seconds * 1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()
        self.selected_pid = None
        self.selected_proc = None

    def refresh(self):
        try:
            self.all_processes = get_processes()
            self.filter_processes()
        except Exception as e:
            try:
                self.details_text.setText(f"Error loading processes: {e}")
            except Exception:
                pass

    def filter_processes(self):
        search_text = self.search_input.text().lower()
        filter_type = self.filter_combo.currentText()
        
        system_like = {
            'system', 'system idle process', 'registry', 'smss.exe', 'csrss.exe',
            'wininit.exe', 'services.exe', 'lsass.exe', 'winlogon.exe', 'svchost.exe',
            'dwm.exe', 'fontdrvhost.exe', 'sihost.exe', 'taskhostw.exe', 'runtimebroker.exe'
        }
        
        filtered = []
        for proc in self.all_processes:
            name = (proc.get('name') or '').lower()
            if name in system_like:
                continue
            # Also skip if looks like core system
            if 'ntoskrnl' in name or 'winlogon' in name or 'csrss' in name:
                continue
            
            if search_text and search_text not in name:
                continue
            
            if filter_type == "User Applications":
                try:
                    classification = classify_process(proc)
                    if classification.get('category') != "User application":
                        continue
                except Exception:
                    continue
            elif filter_type == "High Memory (>100MB)":
                if (proc.get('memory_rss', 0) or 0) < 100 * 1024 * 1024:
                    continue
            elif filter_type == "High CPU (>10%)":
                try:
                    if float(proc.get('cpu_percent', 0) or 0) < 10.0:
                        continue
                except Exception:
                    continue
            
            filtered.append(proc)
        
        try:
            self.model.set_processes(filtered)
            self.table.resizeColumnsToContents()
        except Exception:
            pass

    def show_process_details(self, index):
        if not index.isValid():
            return
        src_index = self.proxy.mapToSource(index)
        proc = self.model.get_process_at(src_index.row())
        if not proc:
            return
        self.selected_pid = proc['pid']
        self.selected_proc = proc
        try:
            classification = classify_process(proc)
        except Exception as e:
            classification = {"category": "Unknown", "risk_level": "Unknown", "importance": "Unknown", "confidence": 0, "explanation": str(e), "can_terminate": False, "evidence": []}
        
        details = []
        details.append(f"Name: {proc.get('name')}")
        details.append(f"PID: {proc.get('pid')} | PPID: {proc.get('ppid')}")
        details.append(f"User: {proc.get('username')}")
        details.append(f"Status: {proc.get('status')}")
        details.append(f"CPU: {proc.get('cpu_percent', 0):.1f}% | Memory: {(proc.get('memory_rss', 0) or 0) // (1024**2)} MiB")
        details.append(f"Started: {proc.get('start_time') or 'Unknown'}")
        details.append(f"Executable: {proc.get('exe') or 'Unknown'}")
        details.append(f"\n--- Classification ---")
        details.append(f"Category: {classification.get('category')}")
        details.append(f"Risk Level: {classification.get('risk_level')}")
        details.append(f"Importance: {classification.get('importance')}")
        details.append(f"Confidence: {classification.get('confidence', 0):.0%}")
        details.append(f"Can Terminate: {'Yes' if classification.get('can_terminate') else 'No'}")
        details.append(f"\nExplanation: {classification.get('explanation')}")
        details.append(f"\nEvidence:")
        for ev in classification.get('evidence', []):
            details.append(f"  • {ev}")
        
        self.details_text.setText("\n".join(details))
        
        if classification.get('can_terminate'):
            self.close_btn.setEnabled(True)
            self.force_kill_btn.setEnabled(True)
        else:
            self.close_btn.setEnabled(False)
            self.force_kill_btn.setEnabled(False)

    def close_selected_process(self):
        if self.selected_pid is None:
            return
        proc = self.selected_proc or next((p for p in self.all_processes if p['pid'] == self.selected_pid), None)
        if not proc:
            return
        try:
            classification = classify_process(proc)
        except Exception:
            classification = {"category": "Unknown", "risk_level": "Unknown", "explanation": ""}
        reply = QMessageBox.question(
            self, "Confirm Close Application",
            f"Are you sure you want to close {proc['name']} (PID: {proc['pid']})?\n\n"
            f"Category: {classification['category']}\n"
            f"Risk: {classification['risk_level']}\n\n"
            f"{classification['explanation']}\n\n"
            f"This will attempt a graceful close first.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                result = process_action_manager.graceful_close(self.selected_pid)
                if result.get('success'):
                    QMessageBox.information(self, "Success", result.get('message'))
                    self.refresh()
                elif result.get('needs_force'):
                    reply2 = QMessageBox.question(
                        self, "Process Not Responding",
                        "The process did not exit gracefully. Try force kill?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if reply2 == QMessageBox.Yes:
                        self.force_kill_selected_process()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def force_kill_selected_process(self):
        if self.selected_pid is None:
            return
        proc = self.selected_proc or next((p for p in self.all_processes if p['pid'] == self.selected_pid), None)
        if not proc:
            return
        try:
            classification = classify_process(proc)
        except Exception:
            classification = {"category": "Unknown", "risk_level": "Unknown", "explanation": ""}
        reply = QMessageBox.warning(
            self, "Confirm Force Kill (Advanced)",
            f"WARNING: Force killing {proc['name']} (PID: {proc['pid']}) can cause data loss!\n\n"
            f"Category: {classification['category']}\n"
            f"Risk: {classification['risk_level']}\n\n"
            f"{classification['explanation']}\n\n"
            f"Are you absolutely sure?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                result = process_action_manager.force_kill(self.selected_pid)
                if result.get('success'):
                    QMessageBox.information(self, "Success", result.get('message'))
                    self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

