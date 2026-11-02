"""Dialogs for reviewing and reporting Storage cleanup actions."""

from typing import Dict, Iterable, List

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


def _format_size(value: int) -> str:
    number = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1024:
            return f"{number:.1f} {unit}"
        number /= 1024
    return f"{number:.1f} PB"


def _unique_paths(paths: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _make_table(headers):
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.NoSelection)
    table.setWordWrap(False)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setStyleSheet("""
        QTableWidget {
            background-color: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            gridline-color: #f3f4f6;
        }
        QHeaderView::section {
            background-color: #f9fafb;
            padding: 6px;
            border: none;
            border-right: 1px solid #e5e7eb;
            border-bottom: 1px solid #e5e7eb;
            font-weight: 600;
        }
    """)
    return table


def _set_row(table, row, values, tooltip_column=0):
    for column, value in enumerate(values):
        item = QTableWidgetItem(str(value))
        if column == tooltip_column:
            item.setToolTip(str(value))
        table.setItem(row, column, item)


class CleanupReviewDialog(QDialog):
    """Pre-cleanup review of every eligible and rejected path."""

    def __init__(self, preview, sizes: Dict[str, int], parent=None):
        super().__init__(parent)
        self.setObjectName("cleanupReviewDialog")
        self.setWindowTitle("Review Cleanup")
        self.setModal(True)
        self.resize(780, 540)

        self._eligible = _unique_paths(preview.get("allowed", []))
        self._rejected = self._unique_rejections(
            preview.get("rejected", [])
        )
        self._sizes = {str(key): value for key, value in (sizes or {}).items()}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        title = QLabel("Review Cleanup")
        title.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #111827;"
        )
        layout.addWidget(title)

        total_size = sum(
            self._sizes.get(path, 0) for path in self._eligible
        )
        self.summary_label = QLabel(
            f"{len(self._eligible)} files eligible | "
            f"Estimated reclaimable size: {_format_size(total_size)}"
        )
        self.summary_label.setStyleSheet("color: #374151; font-size: 12px;")
        layout.addWidget(self.summary_label)

        eligible_label = QLabel("Eligible files")
        eligible_label.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #111827;"
        )
        layout.addWidget(eligible_label)

        self.eligible_table = _make_table(["Path", "Size"])
        self.eligible_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.eligible_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        for row, path in enumerate(self._eligible):
            size = self._sizes.get(path)
            self.eligible_table.insertRow(row)
            _set_row(
                self.eligible_table,
                row,
                [path, _format_size(size) if size is not None else "Unknown"],
            )
        layout.addWidget(self.eligible_table, 3)

        rejected_label = QLabel("Rejected files")
        rejected_label.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #111827;"
        )
        layout.addWidget(rejected_label)

        self.rejected_table = _make_table(["Path", "Reason"])
        self.rejected_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.rejected_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        for row, item in enumerate(self._rejected):
            self.rejected_table.insertRow(row)
            _set_row(
                self.rejected_table,
                row,
                [item.get("path", ""), item.get("reason", "")],
            )
        layout.addWidget(self.rejected_table, 2)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setStyleSheet(
            "padding: 7px 12px; border-radius: 6px; "
            "background-color: #f3f4f6; color: #111827; "
            "border: 1px solid #d1d5db;"
        )
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)

        self.confirm_button = QPushButton(
            f"Move {len(self._eligible)} files to Recycle Bin"
            if self._eligible
            else "Close"
        )
        self.confirm_button.setEnabled(bool(self._eligible))
        self.confirm_button.setStyleSheet(
            "padding: 7px 12px; border-radius: 6px; "
            "background-color: #dc2626; color: #ffffff; border: none;"
        )
        self.confirm_button.clicked.connect(self.accept)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)

    @property
    def eligible_paths(self) -> List[str]:
        return list(self._eligible)

    @staticmethod
    def _unique_rejections(rejected):
        seen = set()
        result = []
        for item in rejected:
            key = (str(item.get("path", "")), str(item.get("reason", "")))
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result


class CleanupResultDialog(QDialog):
    """Post-cleanup per-file outcome report."""

    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.setObjectName("cleanupResultDialog")
        self.setWindowTitle("Cleanup Results")
        self.setModal(True)
        self.resize(780, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        title = QLabel("Cleanup Results")
        title.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #111827;"
        )
        layout.addWidget(title)

        moved = int(result.get("moved", 0))
        failed = int(result.get("failed", 0))
        self.summary_label = QLabel(
            f"Moved {moved} file(s) to Recycle Bin. "
            f"Skipped or failed: {failed}."
        )
        self.summary_label.setStyleSheet("color: #374151; font-size: 12px;")
        layout.addWidget(self.summary_label)

        self.outcomes_table = _make_table(["Path", "Status", "Reason"])
        self.outcomes_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.outcomes_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.outcomes_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        for row, outcome in enumerate(result.get("outcomes", [])):
            status = str(outcome.get("status", "failed")).capitalize()
            self.outcomes_table.insertRow(row)
            _set_row(
                self.outcomes_table,
                row,
                [
                    outcome.get("path", ""),
                    status,
                    outcome.get("reason", ""),
                ],
            )
        layout.addWidget(self.outcomes_table, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close_button = QPushButton("Close")
        close_button.setStyleSheet(
            "padding: 7px 12px; border-radius: 6px; "
            "background-color: #2563eb; color: #ffffff; border: none;"
        )
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
