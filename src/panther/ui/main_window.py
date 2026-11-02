"""Panther System Intelligence UI - main window.

Provides a QMainWindow with a permanent left-sidebar navigation list.
The central widget is a stacked widget that hosts all screens.
"""

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QLabel,
)
from PySide6.QtCore import Qt

from .navigation import NAV_ITEMS
from .dashboard import DashboardScreen
from .processes import ProcessesScreen
from .startup import StartupScreen
from .battery import BatteryScreen
from .recommendations import RecommendationsScreen
from .history import HistoryScreen
from .storage import StorageScreen
from .applications import ApplicationsScreen
from .settings import SettingsScreen


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Panther System Intelligence")
        self.resize(1150, 780)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f7f9fc;
            }
            QListWidget {
                background-color: #111827;
                color: #e5e7eb;
                border: none;
                font-size: 13px;
                padding: 8px 0px;
            }
            QListWidget::item {
                padding: 11px 22px;
                border: none;
                margin: 2px 8px;
                border-radius: 8px;
            }
            QListWidget::item:selected {
                background-color: #2563eb;
                color: #ffffff;
            }
            QListWidget::item:hover:!selected {
                background-color: #1f2937;
                color: #ffffff;
            }
            QStackedWidget {
                background-color: #f7f9fc;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(230)
        for name, _icon in NAV_ITEMS:
            item = QListWidgetItem(name)
            self.sidebar.addItem(item)
        layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()

        _screen_map = {
            "Dashboard": DashboardScreen,
            "Processes": ProcessesScreen,
            "Storage": StorageScreen,
            "Battery": BatteryScreen,
            "Startup Apps": StartupScreen,
            "Applications": ApplicationsScreen,
            "Recommendations": RecommendationsScreen,
            "Activity History": HistoryScreen,
            "Settings": SettingsScreen,
        }

        for name, _icon in NAV_ITEMS:
            cls = _screen_map.get(name)
            if cls is not None:
                widget = cls()
            else:
                placeholder = QLabel(f"{name} screen - coming soon")
                placeholder.setAlignment(Qt.AlignCenter)
                widget = placeholder
            self.stack.addWidget(widget)

        layout.addWidget(self.stack)

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)
