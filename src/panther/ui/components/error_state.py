"""Recoverable error panel with a retry action."""

from PySide6.QtCore import Signal

from .empty_state import EmptyState


class ErrorState(EmptyState):
    """An error explanation plus an explicit retry affordance."""

    retry_requested = Signal()

    def __init__(
        self,
        title: str = "Something went wrong",
        description: str = "",
        action_text: str = "Try again",
        parent=None,
    ):
        super().__init__(
            title=title,
            description=description,
            action_text=action_text or "Try again",
            variant="empty",
            parent=parent,
        )
        self.setObjectName("errorState")
        self.retry_button = self.action_button
        self.action_triggered.connect(self.retry_requested.emit)
