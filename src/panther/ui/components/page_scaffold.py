"""Page shell combining a standard header with a content area."""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from .page_header import PageHeader


class PageScaffold(QWidget):
    """Header + content container for screens that adopt the design system."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent=None,
        margins: int = 24,
        spacing: int = 24,
    ):
        super().__init__(parent)
        self.setObjectName("pageScaffold")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(margins, margins, margins, margins)
        layout.setSpacing(spacing)

        self.header = PageHeader(title, subtitle)
        layout.addWidget(self.header)

        self.content = QWidget()
        self.content.setObjectName("pageContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(spacing)
        layout.addWidget(self.content, 1)

    def set_title(self, title: str) -> None:
        self.header.set_title(title)

    def set_subtitle(self, subtitle: str) -> None:
        self.header.set_subtitle(subtitle)

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self.content_layout.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self.content_layout.addLayout(layout, stretch)
