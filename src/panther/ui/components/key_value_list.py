"""Definition-list style details panel for structured key/value data."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLabel, QWidget


class KeyValueList(QWidget):
    """Rows of label/value pairs, replacing HTML in a single QLabel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("keyValueList")
        self.setAccessibleName("Details")

        self._form = QFormLayout(self)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setSpacing(8)
        self._form.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._rows = {}

    def add_row(self, key: str, value: str = "") -> QLabel:
        text = str(key)
        if text in self._rows:
            raise ValueError(f"Duplicate key: {key}")

        label = QLabel(text)
        label.setObjectName("keyValueLabel")
        label.setWordWrap(True)

        value_label = QLabel(str(value))
        value_label.setObjectName("keyValueValue")
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self._form.addRow(label, value_label)
        self._rows[text] = (label, value_label)
        return value_label

    def keys(self):
        return list(self._rows.keys())

    def value(self, key: str):
        row = self._rows.get(str(key))
        return None if row is None else row[1].text()

    def label_for(self, key: str):
        row = self._rows.get(str(key))
        return None if row is None else row[0]

    def value_label(self, key: str):
        row = self._rows.get(str(key))
        return None if row is None else row[1]

    def set_value(self, key: str, value: str) -> None:
        row = self._rows.get(str(key))
        if row is None:
            return
        row[1].setText(str(value))

    def clear(self) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
        self._rows.clear()
