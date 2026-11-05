"""Standard table view that preserves the existing RecordTableView stack."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHeaderView,
    QStyledItemDelegate,
    QVBoxLayout,
)

from ..table_models import RecordTableView
from .empty_state import EmptyState
from .error_state import ErrorState
from .loading_state import LoadingState

STATES = ("ready", "loading", "empty", "error")


class _RightAlignDelegate(QStyledItemDelegate):
    """Right-align numeric cells without changing the shared model."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignRight | Qt.AlignVCenter


class DataTable(RecordTableView):
    """RecordTableView with a state overlay and column-layout helpers.

    All model, proxy, selection and compatibility helpers are inherited, so
    existing ``RecordTableModel`` / ``RecordFilterProxyModel`` behaviour is
    unchanged.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dataTable")
        self.setAccessibleName("Data table")
        self._column_config = None
        self._numeric_columns = ()
        self._align_delegates = {}
        self._state = "ready"

        overlay = QFrame(self.viewport())
        overlay.setObjectName("tableStateOverlay")
        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setContentsMargins(16, 16, 16, 16)
        overlay_layout.setSpacing(8)

        self.empty_state = EmptyState()
        self.loading_state = LoadingState()
        self.error_state = ErrorState()
        for state_widget in (
            self.empty_state,
            self.loading_state,
            self.error_state,
        ):
            state_widget.hide()
            overlay_layout.addWidget(state_widget)

        overlay.hide()
        self.state_overlay = overlay

    # -- state ------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str, message: str = "") -> None:
        normalized = str(state).lower()
        if normalized not in STATES:
            raise ValueError(f"Unknown table state: {state}")
        self._state = normalized

        self.empty_state.hide()
        self.loading_state.hide()
        self.error_state.hide()

        if normalized == "empty":
            self.empty_state.set_title(message or "Nothing to show")
            self.empty_state.set_description(
                "Adjust the filters or run a scan to populate this table."
            )
            self.empty_state.show()
        elif normalized == "loading":
            self.loading_state.set_message(message or "Loading…")
            self.loading_state.start()
            self.loading_state.show()
        elif normalized == "error":
            self.error_state.set_title(message or "Something went wrong")
            self.error_state.show()

        if normalized == "ready":
            self.state_overlay.hide()
        else:
            self.state_overlay.raise_()
            self.state_overlay.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.state_overlay.setGeometry(self.viewport().rect())

    # -- columns ----------------------------------------------------------

    def setModel(self, model):
        super().setModel(model)
        self._apply_column_config()
        self._apply_numeric_columns()

    def configure_columns(
        self,
        stretch=(),
        resize_to_contents=(),
        hidden=(),
        numeric=(),
    ) -> None:
        self._column_config = (
            tuple(int(column) for column in stretch),
            tuple(int(column) for column in resize_to_contents),
            tuple(int(column) for column in hidden),
        )
        self._numeric_columns = tuple(int(column) for column in numeric)
        self._apply_column_config()
        self._apply_numeric_columns()

    def numeric_columns(self):
        return self._numeric_columns

    def _column_count(self) -> int:
        model = self.model()
        if model is None:
            return 0
        return model.columnCount()

    def _apply_column_config(self) -> None:
        if self._column_config is None:
            return

        stretch, resize_to_contents, hidden = self._column_config
        count = self._column_count()
        if count <= 0:
            return

        header = self.horizontalHeader()
        for column in stretch:
            if 0 <= column < count:
                header.setSectionResizeMode(column, QHeaderView.Stretch)
        for column in resize_to_contents:
            if 0 <= column < count:
                header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        for column in hidden:
            if 0 <= column < count:
                self.setColumnHidden(column, True)

    def _apply_numeric_columns(self) -> None:
        count = self._column_count()
        wanted = {
            column for column in self._numeric_columns if 0 <= column < count
        }

        for column in tuple(self._align_delegates):
            if column not in wanted:
                self.setItemDelegateForColumn(column, None)
                del self._align_delegates[column]

        for column in wanted:
            if column not in self._align_delegates:
                delegate = _RightAlignDelegate(self)
                self.setItemDelegateForColumn(column, delegate)
                self._align_delegates[column] = delegate
