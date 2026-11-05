"""History screen – read-only activity log with search and event details.

Uses :func:`panther.services.history.get_recent` to fetch rows from the SQLite
``history`` table.  The screen formats timestamps for reading, filters rows by
free text or category, and shows the selected event in a details panel.
"""

import datetime

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    QTimer,
)
from PySide6.QtWidgets import (
    QComboBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import config
from ..services.history import get_recent
from .components import (
    Badge,
    DataTable,
    EmptyState,
    ErrorState,
    FilterBar,
    KeyValueList,
    LoadingState,
    PageScaffold,
    SectionCard,
)

ALL_CATEGORIES = "All categories"


def format_timestamp(value) -> str:
    """Render an ISO-style timestamp in a readable, locale-independent form."""

    text = str(value).strip()
    if not text:
        return ""
    try:
        parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text.replace("T", " ")
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


class HistoryTableModel(QAbstractTableModel):
    def __init__(self, rows=None):
        super().__init__()
        self.headers = ["ID", "Timestamp", "Category", "Detail"]
        self._rows = rows or []

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        row = self._rows[index.row()]
        col = index.column()
        value = row[col]
        if col == 1:
            return format_timestamp(value)
        return value

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]
        return super().headerData(section, orientation, role)


class HistoryFilterProxyModel(QSortFilterProxyModel):
    """Free-text filtering across every column plus a category constraint."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._category = ""

    def set_category(self, category: str) -> None:
        normalized = str(category or "")
        if normalized == ALL_CATEGORIES:
            normalized = ""
        if normalized == self._category:
            return

        # Qt 6.10 introduced the explicit filter-change bracket.  Fall back
        # to invalidateFilter() for the supported older PySide6 releases.
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            self._category = normalized
            self.endFilterChange()
        else:  # pragma: no cover - exercised by older Qt versions
            self._category = normalized
            self.invalidateFilter()

    def category(self) -> str:
        return self._category

    def filterAcceptsRow(self, source_row, source_parent):
        if self._category:
            model = self.sourceModel()
            index = model.index(source_row, 2, source_parent)
            if str(index.data(Qt.DisplayRole) or "") != self._category:
                return False
        return super().filterAcceptsRow(source_row, source_parent)


CATEGORY_STATUS = {
    "security": "warning",
    "error": "critical",
    "critical": "critical",
    "action": "success",
    "startup": "info",
    "storage": "info",
    "metric": "neutral",
}


class HistoryScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("historyScreen")
        self._rows = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scaffold = PageScaffold(
            "Activity History",
            "Recent activity recorded by Panther.",
        )
        layout.addWidget(self.scaffold)

        self.filter_bar = FilterBar("Search activity…")
        self.filter_bar.search_changed.connect(self._apply_filter)

        self.category_filter = QComboBox()
        self.category_filter.setObjectName("historyCategoryFilter")
        self.category_filter.setAccessibleName("Filter by category")
        self.category_filter.addItem(ALL_CATEGORIES)
        self.category_filter.currentTextChanged.connect(self._apply_category)
        self.filter_bar.add_widget(self.category_filter)

        self.table = DataTable()
        self.table.configure_columns(
            stretch=(3,), resize_to_contents=(1, 2), numeric=(0,)
        )

        self.proxy_model = HistoryFilterProxyModel(self)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.setSourceModel(HistoryTableModel([]))
        self.table.setModel(self.proxy_model)
        self.table.selectionModel().selectionChanged.connect(
            self._show_selected_details
        )

        self.empty_state = EmptyState(
            "No activity has been recorded yet",
            "Actions and scanned results appear here once Panther records them.",
        )
        self.loading_state = LoadingState("Loading activity history…")
        self.error_state = ErrorState(
            "Could not load activity history",
            "The history service returned an error.",
        )
        self.error_state.retry_requested.connect(self.refresh)

        self.state_stack = QStackedWidget()
        self.state_stack.setObjectName("historyStateStack")
        self.state_stack.addWidget(self.table)
        self.state_stack.addWidget(self.empty_state)
        self.state_stack.addWidget(self.loading_state)
        self.state_stack.addWidget(self.error_state)

        self.details_card = SectionCard("Event details")
        self.details_badge = Badge("No selection", "neutral")
        self.details_card.add_widget(self.details_badge)
        self.details = KeyValueList()
        for key in ("Record", "Timestamp", "Category", "Detail"):
            self.details.add_row(key, "—")
        self.details_card.add_widget(self.details)

        self.scaffold.content_layout.addWidget(self.filter_bar)
        self.scaffold.content_layout.addWidget(self.state_stack, 1)
        self.scaffold.content_layout.addWidget(self.details_card)

        self.timer = QTimer(self)
        self.timer.setInterval(config.refresh_interval_seconds * 1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    # -- filtering -------------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        self.proxy_model.setFilterFixedString(str(text))

    def _apply_category(self, category: str) -> None:
        self.proxy_model.set_category(category)

    def _set_model(self, rows) -> None:
        self._rows = list(rows or [])
        self.proxy_model.setSourceModel(HistoryTableModel(self._rows))
        self._rebuild_category_filter()
        self.proxy_model.set_category(self.category_filter.currentText())
        self._apply_filter(self.filter_bar.search_text())
        self._clear_details()

    def _rebuild_category_filter(self) -> None:
        categories = sorted({str(row[2]) for row in self._rows})
        current = self.category_filter.currentText()
        blocked = self.category_filter.blockSignals(True)
        try:
            self.category_filter.clear()
            self.category_filter.addItem(ALL_CATEGORIES)
            for category in categories:
                self.category_filter.addItem(category)
            index = self.category_filter.findText(current)
            self.category_filter.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self.category_filter.blockSignals(blocked)

    # -- details ---------------------------------------------------------

    def _clear_details(self) -> None:
        for key in ("Record", "Timestamp", "Category", "Detail"):
            self.details.set_value(key, "—")
        self.details_badge.set_text("No selection")
        self.details_badge.set_status("neutral")

    def _show_selected_details(self, *_args) -> None:
        selection = self.table.selectionModel()
        if selection is None:
            return
        rows = selection.selectedRows()
        if not rows:
            return
        index = rows[0]
        category = str(index.siblingAtColumn(2).data() or "")
        self.details.set_value("Record", str(index.siblingAtColumn(0).data()))
        self.details.set_value(
            "Timestamp", str(index.siblingAtColumn(1).data())
        )
        self.details.set_value("Category", category)
        self.details.set_value("Detail", str(index.siblingAtColumn(3).data()))
        self.details_badge.set_text(category or "Unknown")
        self.details_badge.set_status(
            CATEGORY_STATUS.get(category.lower(), "neutral")
        )

    # -- refresh ---------------------------------------------------------

    def _show(self, widget) -> None:
        self.state_stack.setCurrentWidget(widget)

    def refresh(self) -> None:
        self._show(self.loading_state)

        try:
            rows = get_recent(100)
        except Exception as exc:
            self._set_model([])
            self.error_state.set_title("Could not load activity history")
            self.error_state.set_description(str(exc))
            self._show(self.error_state)
            return

        self._set_model(rows or [])
        if rows:
            self._show(self.table)
        else:
            self._show(self.empty_state)
