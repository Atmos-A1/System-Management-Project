"""Startup screen – read-only view of Windows Run-key entries.

All heavy work is delegated to
:func:`panther.services.startup_adapter.get_startup_entries`.  The adapter
raises :class:`UnsupportedPlatformError` on platforms without the Windows
registry; that state is reported explicitly instead of being presented as an
empty list.
"""

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from ..services.startup_adapter import UnsupportedPlatformError, get_startup_entries
from .components import (
    DataTable,
    EmptyState,
    ErrorState,
    FilterBar,
    LoadingState,
    PageScaffold,
)


class StartupTableModel(QAbstractTableModel):
    def __init__(self, entries=None):
        super().__init__()
        self.headers = ["Name", "Command", "Scope"]
        self._data = entries or []

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        entry = self._data[index.row()]
        col = index.column()
        if col == 0:
            return entry.get("name")
        if col == 1:
            return entry.get("command")
        if col == 2:
            return entry.get("scope")
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]
        return super().headerData(section, orientation, role)


class StartupScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("startupScreen")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scaffold = PageScaffold(
            "Startup Apps",
            "Programs configured to run when Windows starts.",
        )
        layout.addWidget(self.scaffold)

        self.filter_bar = FilterBar("Search startup entries…")
        self.filter_bar.search_changed.connect(self._apply_filter)

        self.table = DataTable()
        self.table.configure_columns(stretch=(1,), resize_to_contents=(0, 2))

        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.setSourceModel(StartupTableModel([]))
        self.table.setModel(self.proxy_model)

        self.unsupported_state = EmptyState(
            "Startup Apps is not available on this platform",
            "Startup app management requires the Windows registry, which is "
            "not available on this platform.",
            variant="unsupported",
        )
        self.empty_state = EmptyState(
            "No startup entries were found",
            "No entries were found in the current-user or machine Run keys.",
        )
        self.loading_state = LoadingState("Reading startup entries…")
        self.error_state = ErrorState(
            "Could not read startup entries",
            "The startup service returned an error.",
        )
        self.error_state.retry_requested.connect(self.refresh)

        self.state_stack = QStackedWidget()
        self.state_stack.setObjectName("startupStateStack")
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

    def _set_model(self, entries) -> None:
        self.proxy_model.setSourceModel(StartupTableModel(entries))
        self._apply_filter(self.filter_bar.search_text())

    def _show(self, widget) -> None:
        self.state_stack.setCurrentWidget(widget)

    def refresh(self) -> None:
        self.filter_bar.show()
        self._show(self.loading_state)

        try:
            entries = get_startup_entries()
        except UnsupportedPlatformError:
            self._set_model([])
            self.filter_bar.hide()
            self._show(self.unsupported_state)
            return
        except Exception as exc:
            self._set_model([])
            self.error_state.set_title("Could not read startup entries")
            self.error_state.set_description(str(exc))
            self._show(self.error_state)
            return

        self._set_model(entries or [])
        if entries:
            self._show(self.table)
        else:
            self._show(self.empty_state)
