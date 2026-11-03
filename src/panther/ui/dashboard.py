"""Dashboard screen - modern system overview.

Shows RAM, CPU, Disk and Battery summary cards with visual styling.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QGridLayout, 
    QProgressBar
)
from PySide6.QtCore import QTimer, Qt

from ..config import config
from ..services.system_monitor import (
    get_cpu_percent,
    get_ram_usage,
    get_disk_usage,
    get_battery_info,
)


class DashboardScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("dashboardScreen")
        self.setStyleSheet("""
            QWidget {
                background-color: #f7f9fc;
            }
            QFrame#card {
                background-color: #ffffff;
                border-radius: 12px;
                border: 1px solid #e5e7eb;
            }
            QLabel#cardTitle {
                font-size: 13px;
                font-weight: 600;
                color: #1f2937;
            }
            QLabel#cardValue {
                font-size: 32px;
                font-weight: 700;
                color: #2563eb;
            }
            QLabel#cardDetail {
                font-size: 11px;
                color: #6b7280;
            }
            QLabel#headerTitle {
                font-size: 24px;
                font-weight: 700;
                color: #111827;
            }
            QLabel#headerSubtitle {
                font-size: 12px;
                color: #6b7280;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        # Header
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        
        title = QLabel("System Dashboard")
        title.setObjectName("headerTitle")
        subtitle = QLabel("Real-time monitoring of your system resources")
        subtitle.setObjectName("headerSubtitle")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        # Cards grid
        grid = QGridLayout()
        grid.setSpacing(16)
        grid.setContentsMargins(0, 0, 0, 0)
        
        self.cpu_card = self.create_card("CPU", "0%")
        self.ram_card = self.create_card("Memory (RAM)", "0%")
        self.disk_card = self.create_card("Storage", "0%")
        self.battery_card = self.create_card("Battery", "N/A")
        self.cpu_label = self.cpu_card.value_label
        self.ram_label = self.ram_card.value_label
        self.disk_label = self.disk_card.value_label
        self.battery_label = self.battery_card.value_label
        self.cpu_detail_label = self.cpu_card.detail_label
        self.ram_detail_label = self.ram_card.detail_label
        self.disk_detail_label = self.disk_card.detail_label
        self.battery_detail_label = self.battery_card.detail_label
        
        grid.addWidget(self.cpu_card, 0, 0)
        grid.addWidget(self.ram_card, 0, 1)
        grid.addWidget(self.disk_card, 1, 0)
        grid.addWidget(self.battery_card, 1, 1)
        
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch()

        # Timer for periodic refresh
        self.timer = QTimer(self)
        self.timer.setInterval(config.refresh_interval_seconds * 1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def create_card(self, title, value):
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumHeight(170)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 18, 22, 18)
        card_layout.setSpacing(10)
        
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        
        value_label = QLabel(value)
        value_label.setObjectName("cardValue")
        value_label.setAlignment(Qt.AlignCenter)
        
        detail_label = QLabel("")
        detail_label.setObjectName("cardDetail")
        detail_label.setAlignment(Qt.AlignCenter)
        detail_label.setWordWrap(True)
        
        progress = QProgressBar()
        progress.setTextVisible(False)
        progress.setFixedHeight(8)
        progress.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #f1f5f9;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #2563eb;
                border-radius: 4px;
            }
        """)
        
        card_layout.addWidget(title_label)
        card_layout.addSpacing(6)
        card_layout.addWidget(value_label)
        card_layout.addWidget(detail_label)
        card_layout.addSpacing(10)
        card_layout.addWidget(progress)
        
        card.value_label = value_label
        card.detail_label = detail_label
        card.progress = progress
        card.title = title
        
        return card

    def refresh(self):
        # CPU
        try:
            cpu = get_cpu_percent()
            self.cpu_card.value_label.setText(f"{cpu:.1f}%")
            self.cpu_card.detail_label.setText("Processor Usage")
            self.cpu_card.progress.setValue(int(max(0, min(100, cpu))))
            if cpu > 85:
                self.cpu_card.progress.setStyleSheet("""
                    QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #dc2626; border-radius: 4px; }
                """)
            elif cpu > 65:
                self.cpu_card.progress.setStyleSheet("""
                    QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #f59e0b; border-radius: 4px; }
                """)
            else:
                self.cpu_card.progress.setStyleSheet("""
                    QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #22c55e; border-radius: 4px; }
                """)
        except Exception:
            self.cpu_card.value_label.setText("N/A")
            self.cpu_card.detail_label.setText("Unavailable")
            self.cpu_card.progress.setValue(0)

        # RAM
        try:
            ram = get_ram_usage()
            used_gb = ram['used'] / (1024**3)
            total_gb = ram['total'] / (1024**3)
            self.ram_card.value_label.setText(f"{ram['percent']:.1f}%")
            self.ram_card.detail_label.setText(f"{used_gb:.1f} GB / {total_gb:.1f} GB")
            self.ram_card.progress.setValue(int(max(0, min(100, ram['percent']))))
            if ram['percent'] > 90:
                self.ram_card.progress.setStyleSheet("""
                    QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #dc2626; border-radius: 4px; }
                """)
            elif ram['percent'] > 80:
                self.ram_card.progress.setStyleSheet("""
                    QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #f59e0b; border-radius: 4px; }
                """)
            else:
                self.ram_card.progress.setStyleSheet("""
                    QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #22c55e; border-radius: 4px; }
                """)
        except Exception:
            self.ram_card.value_label.setText("N/A")
            self.ram_card.detail_label.setText("Unavailable")
            self.ram_card.progress.setValue(0)

        # Disk
        try:
            disk = get_disk_usage()
            used_gb = disk['used'] / (1024**3)
            total_gb = disk['total'] / (1024**3)
            self.disk_card.value_label.setText(f"{disk['percent']:.1f}%")
            self.disk_card.detail_label.setText(f"{used_gb:.1f} GB / {total_gb:.1f} GB")
            self.disk_card.progress.setValue(int(max(0, min(100, disk['percent']))))
            if disk['percent'] > 92:
                self.disk_card.progress.setStyleSheet("""
                    QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #dc2626; border-radius: 4px; }
                """)
            elif disk['percent'] > 85:
                self.disk_card.progress.setStyleSheet("""
                    QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #f59e0b; border-radius: 4px; }
                """)
            else:
                self.disk_card.progress.setStyleSheet("""
                    QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #22c55e; border-radius: 4px; }
                """)
        except Exception:
            self.disk_card.value_label.setText("N/A")
            self.disk_card.detail_label.setText("Unavailable")
            self.disk_card.progress.setValue(0)

        # Battery
        try:
            batt = get_battery_info()
            if batt:
                self.battery_card.value_label.setText(f"{batt['percent']:.0f}%")
                status = "Charging" if batt.get("power_plugged") else "Discharging"
                self.battery_card.detail_label.setText(status)
                self.battery_card.progress.setValue(int(max(0, min(100, batt['percent']))))
                if batt['percent'] < 20 and not batt.get("power_plugged"):
                    self.battery_card.progress.setStyleSheet("""
                        QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                        QProgressBar::chunk { background-color: #dc2626; border-radius: 4px; }
                    """)
                elif batt.get("power_plugged"):
                    self.battery_card.progress.setStyleSheet("""
                        QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                        QProgressBar::chunk { background-color: #22c55e; border-radius: 4px; }
                    """)
                else:
                    self.battery_card.progress.setStyleSheet("""
                        QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                        QProgressBar::chunk { background-color: #2563eb; border-radius: 4px; }
                    """)
            else:
                self.battery_card.value_label.setText("N/A")
                self.battery_card.detail_label.setText("No battery detected")
                self.battery_card.progress.setValue(0)
                self.battery_card.progress.setStyleSheet("""
                    QProgressBar { border: none; background-color: #f1f5f9; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #9ca3af; border-radius: 4px; }
                """)
        except Exception:
            self.battery_card.value_label.setText("N/A")
            self.battery_card.detail_label.setText("Unavailable")
            self.battery_card.progress.setValue(0)
