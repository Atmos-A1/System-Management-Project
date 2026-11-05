"""Reusable confirmation dialog for potentially destructive actions."""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from .buttons import DestructiveButton, PrimaryButton, SecondaryButton


class ConfirmDialog(QDialog):
    """Modal confirmation with a safe default and optional destructive styling."""

    def __init__(
        self,
        title: str,
        message: str,
        confirm_text: str = "Confirm",
        cancel_text: str = "Cancel",
        destructive: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._confirmed = False
        self.setWindowTitle(str(title))
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_label = QLabel(str(title))
        title_label.setObjectName("dialogTitle")
        title_label.setWordWrap(True)

        self.message_label = QLabel(str(message))
        self.message_label.setObjectName("dialogMessage")
        self.message_label.setWordWrap(True)

        self.button_box = QDialogButtonBox()
        if destructive:
            self.confirm_button = DestructiveButton(confirm_text)
        else:
            self.confirm_button = PrimaryButton(confirm_text)
        self.cancel_button = SecondaryButton(cancel_text)
        self.button_box.addButton(
            self.confirm_button, QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.button_box.addButton(
            self.cancel_button, QDialogButtonBox.ButtonRole.RejectRole
        )

        # Cancel is the default so accidental Enter presses do not destroy data.
        self.cancel_button.setDefault(True)
        self.confirm_button.setDefault(False)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout.addWidget(title_label)
        layout.addWidget(self.message_label)
        layout.addWidget(self.button_box)

    @property
    def confirmed(self) -> bool:
        return self._confirmed

    def accept(self) -> None:
        self._confirmed = True
        super().accept()

    def reject(self) -> None:
        self._confirmed = False
        super().reject()

    @staticmethod
    def ask(
        parent,
        title: str,
        message: str,
        confirm_text: str = "Confirm",
        destructive: bool = False,
    ) -> bool:
        dialog = ConfirmDialog(
            title,
            message,
            confirm_text=confirm_text,
            destructive=destructive,
            parent=parent,
        )
        return dialog.exec() == QDialog.DialogCode.Accepted
