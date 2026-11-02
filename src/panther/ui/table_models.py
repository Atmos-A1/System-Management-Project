"""Small shared Qt model/view helpers for Storage result tables.

Records are plain dictionaries owned by the domain/service layer. Models only
format and expose those records; they never perform filesystem I/O.
"""

from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Optional

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QRectF,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
)


PERCENT_ROLE = Qt.UserRole + 2


def format_size(value) -> str:
    try:
        number = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return "0 B"
    if number < 1024:
        return f"{number} B"
    size = float(number)
    for unit in ("KB", "MB", "GB", "TB", "PB"):
        size /= 1024.0
        if size < 1024:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} EB"


@dataclass
class ColumnSpec:
    header: str
    display: Callable[[dict], str]
    sort: Optional[Callable[[dict], Any]] = None
    tooltip: Optional[Callable[[dict], Optional[str]]] = None
    alignment: Optional[Qt.AlignmentFlag] = None


class RecordTableModel(QAbstractTableModel):
    """Expose a list of dictionaries as a table without copying every cell."""

    def __init__(
        self,
        columns: Iterable[ColumnSpec],
        records: Optional[Iterable[dict]] = None,
        search_fields: Iterable[str] = (),
        parent=None,
    ):
        super().__init__(parent)
        self._columns = list(columns)
        self._search_fields = tuple(search_fields)
        self._records: List[dict] = []
        self.set_records(records or [])

    @property
    def columns(self) -> List[ColumnSpec]:
        return list(self._columns)

    @property
    def records(self) -> List[dict]:
        return list(self._records)

    @property
    def record_list(self) -> List[dict]:
        """Underlying list for callers that only read the current result set."""
        return self._records

    def set_records(self, records: Iterable[dict]):
        clean = [item for item in records or [] if isinstance(item, dict)]
        self.beginResetModel()
        self._records = clean
        self.endResetModel()

    def record_at(self, row: int) -> Optional[dict]:
        if 0 <= row < len(self._records):
            return self._records[row]
        return None

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._records)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._columns)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        record = self.record_at(index.row())
        if record is None or not (0 <= index.column() < len(self._columns)):
            return None
        column = self._columns[index.column()]
        if role == Qt.DisplayRole:
            try:
                return column.display(record)
            except Exception:
                return ""
        if role == Qt.ToolTipRole:
            if column.tooltip is not None:
                try:
                    tooltip = column.tooltip(record)
                except Exception:
                    tooltip = None
                if tooltip:
                    return tooltip
            try:
                return column.display(record)
            except Exception:
                return ""
        if role == Qt.UserRole:
            return record
        if role == PERCENT_ROLE:
            return record.get("percentage")
        if role == Qt.TextAlignmentRole and column.alignment is not None:
            return int(column.alignment)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            if 0 <= section < len(self._columns):
                return self._columns[section].header
            return None
        return section + 1

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def sort_key_for_index(self, index: QModelIndex):
        if not index.isValid():
            return ""
        record = self.record_at(index.row())
        if record is None or not (0 <= index.column() < len(self._columns)):
            return ""
        column = self._columns[index.column()]
        if column.sort is not None:
            try:
                return column.sort(record)
            except Exception:
                pass
        try:
            return column.display(record)
        except Exception:
            return ""

    def searchable_text(self, record: dict) -> str:
        if not self._search_fields:
            values = []
            for column in self._columns:
                try:
                    values.append(str(column.display(record)))
                except Exception:
                    continue
            return " ".join(values).casefold()
        values = []
        for field in self._search_fields:
            value = record.get(field, "")
            if value is None:
                continue
            values.append(str(value))
        return " ".join(values).casefold()


class RecordFilterProxyModel(QSortFilterProxyModel):
    """Case-insensitive text filter over a RecordTableModel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_text = ""
        self.setDynamicSortFilter(True)
        self.setSortCaseSensitivity(Qt.CaseInsensitive)

    @property
    def search_text(self) -> str:
        return self._search_text

    def set_search_text(self, text):
        normalized = str(text or "").strip()
        if normalized == self._search_text:
            return
        self._search_text = normalized
        self.invalidate()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._search_text:
            return True
        model = self.sourceModel()
        if model is None or not hasattr(model, "record_at"):
            return True
        record = model.record_at(source_row)
        if record is None:
            return False
        needle = self._search_text.casefold()
        return needle in model.searchable_text(record).casefold()

    def lessThan(self, left, right):
        model = self.sourceModel()
        if model is None or not hasattr(model, "sort_key_for_index"):
            return super().lessThan(left, right)
        left_key = model.sort_key_for_index(left)
        right_key = model.sort_key_for_index(right)
        try:
            return left_key < right_key
        except TypeError:
            return str(left_key) < str(right_key)


class _CellAdapter:
    """Compatibility shim so existing table-reading code keeps working."""

    def __init__(self, view, row, column):
        self._view = view
        self._row = row
        self._column = column

    def _index(self):
        model = self._view.model()
        if model is None:
            return QModelIndex()
        return model.index(self._row, self._column)

    def text(self):
        value = self._index().data(Qt.DisplayRole)
        return "" if value is None else str(value)

    def data(self, role=Qt.UserRole):
        return self._index().data(role)

    def row(self):
        return self._row

    def column(self):
        return self._column

    def toolTip(self):
        value = self._index().data(Qt.ToolTipRole)
        return "" if value is None else str(value)


class RecordTableView(QTableView):
    """Model-backed table view with small compatibility helpers."""

    itemSelectionChanged = Signal()
    itemDoubleClicked = Signal(QModelIndex)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.horizontalHeader().setSortIndicatorShown(True)
        self.doubleClicked.connect(self.itemDoubleClicked.emit)

    def setModel(self, model):
        super().setModel(model)
        selection = self.selectionModel()
        if selection is not None:
            selection.selectionChanged.connect(self._emit_selection)
            selection.currentChanged.connect(self._emit_selection)

    def _emit_selection(self, *_args):
        self.itemSelectionChanged.emit()

    def rowCount(self):
        model = self.model()
        return model.rowCount() if model is not None else 0

    def columnCount(self):
        model = self.model()
        return model.columnCount() if model is not None else 0

    def currentRow(self):
        index = self.currentIndex()
        return index.row() if index.isValid() else -1

    def setCurrentCell(self, row, column):
        model = self.model()
        if model is None:
            return
        index = model.index(row, column)
        if index.isValid():
            self.setCurrentIndex(index)

    def item(self, row, column):
        return _CellAdapter(self, row, column)

    def record_for_index(self, index):
        model = self.model()
        if model is None or not index.isValid():
            return None
        if isinstance(model, QSortFilterProxyModel):
            source_model = model.sourceModel()
            source_index = model.mapToSource(index)
        else:
            source_model = model
            source_index = index
        if source_model is None or not source_index.isValid():
            return None
        if not hasattr(source_model, "record_at"):
            return None
        return source_model.record_at(source_index.row())

    def selected_records(self):
        selection = self.selectionModel()
        if selection is None:
            return []
        records = []
        for index in selection.selectedRows():
            record = self.record_for_index(index)
            if record is not None:
                records.append(record)
        return records

    def visible_records(self):
        model = self.model()
        if model is None:
            return []
        return [
            self.record_for_index(model.index(row, 0))
            for row in range(model.rowCount())
        ]


class DistributionDelegate(QStyledItemDelegate):
    """Draw a compact proportional bar for a percentage column."""

    def paint(self, painter, option, index):
        percentage = index.data(PERCENT_ROLE)
        try:
            percentage = max(0.0, min(100.0, float(percentage or 0.0)))
        except (TypeError, ValueError):
            percentage = 0.0

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(option.rect).adjusted(6, 7, -6, -7)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#f1f5f9"))
        painter.drawRoundedRect(rect, 5, 5)
        if percentage > 0 and rect.width() > 0:
            filled = QRectF(
                rect.left(),
                rect.top(),
                rect.width() * percentage / 100.0,
                rect.height(),
            )
            painter.setBrush(QColor("#2563eb"))
            painter.drawRoundedRect(filled, 5, 5)
        painter.restore()
