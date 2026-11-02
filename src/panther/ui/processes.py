"""Process screen - displays running processes with management capabilities.

Shows process list with classification, allows searching/filtering/sorting,
and provides safe termination options with confirmations.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QPushButton, 
    QLineEdit, QLabel, QComboBox, QSplitter, QTextEdit, QMessageBox,
    QGroupBox, QFormLayout
)
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex, QTimer

from ..services.process_adapter import get_processes
from ..services.process_classifier import classify_process
from ..services.process_actions import process_action_manager
from ..config import config


class ProcessTableModel(QAbstractTableModel):
    def __init__(self, processes=None):
        super().__init__()
        self.headers = ["PID", "Name", "User", "CPU %", "RAM (MiB)", "Status", "Category"]
        self._processes = processes or []
        self._classifications = {}

    def set_processes(self, processes):
        self._processes = processes
        self._classifications = {}
        for p in processes:
            try:
                self._classifications[p['pid']] = classify_process(p)
            except Exception:
                self._classifications[p['pid']] = {
                    "category": "Unknown",
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
                return proc.get('pid')
            elif col == 1:
                return proc.get('name')
            elif col == 2:
                return proc.get('username', '')[:20]
            elif col == 3:
                cpu = proc.get('cpu_percent', 0)
                return f"{cpu:.1f}"
            elif col == 4:
                return f"{proc.get('memory_rss', 0) // (1024**2)}"
            elif col == 5:
                return proc.get('status', '')
            elif col == 6:
                return classification.get('category', 'Unknown')
            return None
        elif role == Qt.ToolTipRole and col == 6:
            return f"Risk: {classification.get('risk_level', 'Unknown')}\n{classification.get('explanation', '')}"
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
        self.all_processes = []
        
        main_layout = QVBoxLayout(self)
        
        # Top bar with search and filters
        top_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search processes by name...")
        self.search_input.textChanged.connect(self.filter_processes)
        top_bar.addWidget(QLabel("Search:"))
        top_bar.addWidget(self.search_input)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "User Applications", "System", "High Memory (>100MB)", "High CPU (>10%)"])
        self.filter_combo.currentTextChanged.connect(self.filter_processes)
        top_bar.addWidget(QLabel("Filter:"))
        top_bar.addWidget(self.filter_combo)
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        top_bar.addWidget(self.refresh_btn)
        
        main_layout.addLayout(top_bar)
        
        # Splitter for table and details
        splitter = QSplitter(Qt.Vertical)
        
        # Table
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        self.table = QTableView()
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.clicked.connect(self.show_process_details)
        self.model = ProcessTableModel()
        self.table.setModel(self.model)
        table_layout.addWidget(self.table)
        splitter.addWidget(table_widget)
        
        # Details panel
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_label = QLabel("Process Details & Actions")
        details_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        details_layout.addWidget(details_label)
        
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(150)
        details_layout.addWidget(self.details_text)
        
        # Action buttons
        actions_layout = QHBoxLayout()
        self.close_btn = QPushButton("Close Application (Graceful)")
        self.close_btn.clicked.connect(self.close_selected_process)
        self.force_kill_btn = QPushButton("Force Kill (Advanced)")
        self.force_kill_btn.clicked.connect(self.force_kill_selected_process)
        self.force_kill_btn.setStyleSheet("background-color: #ff6b6b;")
        actions_layout.addWidget(self.close_btn)
        actions_layout.addWidget(self.force_kill_btn)
        actions_layout.addStretch()
        details_layout.addLayout(actions_layout)
        
        splitter.addWidget(details_widget)
        splitter.setSizes([400, 150])
        main_layout.addWidget(splitter)
        
        # Timer for auto-refresh
        self.timer = QTimer(self)
        self.timer.setInterval(config.refresh_interval_seconds * 1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()
        self.selected_pid = None

    def refresh(self):
        try:
            self.all_processes = get_processes()
            self.filter_processes()
        except Exception as e:
            self.details_text.setText(f"Error loading processes: {e}")

    def filter_processes(self):
        search_text = self.search_input.text().lower()
        filter_type = self.filter_combo.currentText()
        
        filtered = []
        for proc in self.all_processes:
            # Search filter
            if search_text and search_text not in proc.get('name', '').lower():
                continue
            
            # Type filter
            if filter_type == "User Applications":
                classification = classify_process(proc)
                if classification.get('category') != "User application":
                    continue
            elif filter_type == "System":
                classification = classify_process(proc)
                if "system" not in classification.get('category', '').lower():
                    continue
            elif filter_type == "High Memory (>100MB)":
                if proc.get('memory_rss', 0) < 100 * 1024 * 1024:
                    continue
            elif filter_type == "High CPU (>10%)":
                if proc.get('cpu_percent', 0) < 10.0:
                    continue
            
            filtered.append(proc)
        
        self.model.set_processes(filtered)
        self.table.resizeColumnsToContents()

    def show_process_details(self, index):
        if not index.isValid():
            return
        proc = self.model.get_process_at(index.row())
        if not proc:
            return
        self.selected_pid = proc['pid']
        classification = classify_process(proc)
        
        details = []
        details.append(f"Name: {proc.get('name')}")
        details.append(f"PID: {proc.get('pid')} | PPID: {proc.get('ppid')}")
        details.append(f"User: {proc.get('username')}")
        details.append(f"Status: {proc.get('status')}")
        details.append(f"CPU: {proc.get('cpu_percent', 0):.1f}% | Memory: {proc.get('memory_rss', 0) // (1024**2)} MiB")
        details.append(f"Started: {proc.get('start_time') or 'Unknown'}")
        details.append(f"Executable: {proc.get('exe') or 'Unknown'}")
        details.append(f"\n--- Classification ---")
        details.append(f"Category: {classification.get('category')}")
        details.append(f"Risk Level: {classification.get('risk_level')}")
        details.append(f"Importance: {classification.get('importance')}")
        details.append(f"Confidence: {classification.get('confidence'):.0%}")
        details.append(f"Can Terminate: {'Yes' if classification.get('can_terminate') else 'No'}")
        details.append(f"\nExplanation: {classification.get('explanation')}")
        details.append(f"\nEvidence:")
        for ev in classification.get('evidence', []):
            details.append(f"  • {ev}")
        
        self.details_text.setText("\n".join(details))
        
        # Enable/disable buttons based on classification
        if classification.get('can_terminate'):
            self.close_btn.setEnabled(True)
            self.force_kill_btn.setEnabled(True)
        else:
            self.close_btn.setEnabled(False)
            self.force_kill_btn.setEnabled(False)

    def close_selected_process(self):
        if self.selected_pid is None:
            return
        proc = None
        for p in self.all_processes:
            if p['pid'] == self.selected_pid:
                proc = p
                break
        if not proc:
            return
        
        classification = classify_process(proc)
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
        proc = None
        for p in self.all_processes:
            if p['pid'] == self.selected_pid:
                proc = p
                break
        if not proc:
            return
        
        classification = classify_process(proc)
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
