"""Applications screen - lists installed applications.

Displays installed applications with publisher, version, install location
and provides access to uninstaller where available.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableView, QLabel
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex

from ..services.app_inventory import get_installed_apps


class AppTableModel(QAbstractTableModel):
    def __init__(self, apps=None):
        super().__init__()
        self.headers = ["Name", "Publisher", "Version", "Install Location"]
        self._apps = apps or []

    def rowCount(self, parent=QModelIndex()):
        return len(self._apps)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        app = self._apps[index.row()]
        col = index.column()
        if col == 0:
            return app.get("name")
        if col == 1:
            return app.get("publisher")
        if col == 2:
            return app.get("version")
        if col == 3:
            return app.get("install_location")
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]
        return super().headerData(section, orientation, role)


class ApplicationsScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("applicationsScreen")
        layout = QVBoxLayout(self)
        title = QLabel("Installed Applications")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)
        self.table = QTableView()
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self):
        apps = get_installed_apps()
        self.table.setModel(AppTableModel(apps))
        self.table.resizeColumnsToContents()
