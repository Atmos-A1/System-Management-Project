"""Applications screen - installed applications with search and clear states.

The inventory service is the authority on what this platform can report.  The
screen only translates an unavailable service signal into an explicit UI
state; it never fabricates or infers installed applications.
"""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from ..services.app_inventory import get_installed_apps, winreg
from .components import (
    DataTable,
    EmptyState,
    ErrorState,
    FilterBar,
    LoadingState,
    PageScaffold,
)


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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scaffold = PageScaffold(
            "Installed Applications",
            "Applications discovered on this system, with publisher and version.",
        )
        layout.addWidget(self.scaffold)

        self.filter_bar = FilterBar("Search installed applications…")
        self.filter_bar.search_changed.connect(self._apply_filter)

        self.table = DataTable()
        self.table.configure_columns(stretch=(0, 3), resize_to_contents=(1, 2))

        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.setSourceModel(AppTableModel([]))
        self.table.setModel(self.proxy_model)

        self.unsupported_state = EmptyState(
            "Applications inventory is not available on this platform",
            "Reading installed applications requires the Windows registry, "
            "which is not available on this platform.",
            variant="unsupported",
        )
        self.empty_state = EmptyState(
            "No applications were found",
            "The Windows uninstall registry keys did not report any applications.",
        )
        self.loading_state = LoadingState("Reading installed applications…")
        self.error_state = ErrorState(
            "Could not read installed applications",
            "The application inventory service returned an error.",
        )
        self.error_state.retry_requested.connect(self.refresh)

        self.state_stack = QStackedWidget()
        self.state_stack.setObjectName("applicationsStateStack")
        self.state_stack.addWidget(self.table)
        self.state_stack.addWidget(self.unsupported_state)
        self.state_stack.addWidget(self.empty_state)
        self.state_stack.addWidget(self.loading_state)
        self.state_stack.addWidget(self.error_state)

        self.scaffold.content_layout.addWidget(self.filter_bar)
        self.scaffold.content_layout.addWidget(self.state_stack, 1)

        self.refresh()

    def _apply_filter(self, text: str) -> None:
        self.proxy_model.setFilterFixedString(str(text))

    def _set_model(self, apps) -> None:
        self.proxy_model.setSourceModel(AppTableModel(apps))
        self._apply_filter(self.filter_bar.search_text())

    def _show(self, widget) -> None:
        self.state_stack.setCurrentWidget(widget)

    def refresh(self) -> None:
        if winreg is None:
            self._set_model([])
            self.filter_bar.hide()
            self._show(self.unsupported_state)
            return

        self.filter_bar.show()
        self._show(self.loading_state)

        try:
            apps = get_installed_apps()
        except Exception as exc:
            self._set_model([])
            self.error_state.set_title("Could not read installed applications")
            self.error_state.set_description(str(exc))
            self._show(self.error_state)
            return

        self._set_model(apps or [])
        if apps:
            self._show(self.table)
        else:
            self._show(self.empty_state)
