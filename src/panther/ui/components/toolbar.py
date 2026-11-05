"""Horizontal action and filter bars used above data surfaces."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit


class Toolbar(QFrame):
    """Small horizontal container for actions, aligned left or right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolbar")
        self.setAccessibleName("Toolbar")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

    def layout(self):
        return self._layout

    def add_widget(self, widget, stretch: int = 0, align: str = "left"):
        if str(align).lower() == "right":
            self.add_stretch()
        self._layout.addWidget(widget, stretch)
        return widget

    def add_stretch(self, stretch: int = 1):
        self._layout.addStretch(stretch)

    def add_separator(self) -> QFrame:
        separator = QFrame()
        separator.setObjectName("toolbarSeparator")
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Plain)
        separator.setFocusPolicy(Qt.NoFocus)
        self._layout.addWidget(separator)
        return separator


class FilterBar(Toolbar):
    """Toolbar with a standard search field wired to a signal."""

    search_changed = Signal(str)

    def __init__(self, search_placeholder: str = "Search…", parent=None):
        super().__init__(parent)
        self.setObjectName("filterBar")

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("filterSearch")
        self.search_edit.setPlaceholderText(str(search_placeholder))
        self.search_edit.setAccessibleName("Search")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(220)
        self.search_edit.setMaximumWidth(420)
        self.search_edit.textChanged.connect(self.search_changed.emit)

        self._layout.addWidget(self.search_edit)
        self._layout.addStretch(1)

    def search_text(self) -> str:
        return self.search_edit.text()

    def set_search_text(self, text: str) -> None:
        self.search_edit.setText(str(text))
