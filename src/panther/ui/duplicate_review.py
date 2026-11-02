"""Duplicate group review and deliberate copy selection."""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .table_models import (
    ColumnSpec,
    RecordFilterProxyModel,
    RecordTableModel,
    RecordTableView,
)


def _format_size(value: int) -> str:
    number = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1024:
            return f"{number:.1f} {unit}"
        number /= 1024
    return f"{number:.1f} PB"


def _parse_modified(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def _path_sort_key(copy: Dict[str, Any]):
    path = str(copy.get("path", ""))
    return (len(path), path.casefold())


def _group_name(group: Dict[str, Any]) -> str:
    for item in group.get("files", []) or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if name:
            return str(name)
        path = item.get("path")
        if path:
            return os.path.basename(str(path))
    return ""


def _group_search_text(group: Dict[str, Any]) -> str:
    values = []
    for item in group.get("files", []) or []:
        if not isinstance(item, dict):
            continue
        values.append(str(item.get("name", "")))
        values.append(str(item.get("path", "")))
    return " ".join(values).casefold()


class DuplicateSelection:
    """Selection state for one duplicate group.

    The selected records are never mutated; only a set of removal paths is
    maintained. Removal of every copy is always rejected.
    """

    def __init__(self, group: Dict[str, Any]):
        self._group = group if isinstance(group, dict) else {}
        self._copies = [
            dict(item)
            for item in self._group.get("files", []) or []
            if isinstance(item, dict) and item.get("path")
        ]
        self._removals = set()

    @property
    def copies(self) -> List[Dict[str, Any]]:
        return self._copies

    @property
    def removal_paths(self) -> List[str]:
        return [
            str(item["path"])
            for item in self._copies
            if str(item["path"]) in self._removals
        ]

    @property
    def retained_paths(self) -> List[str]:
        return [
            str(item["path"])
            for item in self._copies
            if str(item["path"]) not in self._removals
        ]

    @property
    def removal_count(self) -> int:
        return len(self._removals)

    @property
    def savings(self) -> int:
        return sum(self._size(item) for item in self._copies if str(item["path"]) in self._removals)

    @property
    def removal_sizes(self) -> Dict[str, int]:
        return {
            str(item["path"]): self._size(item)
            for item in self._copies
            if str(item["path"]) in self._removals
        }

    def _size(self, item: Dict[str, Any]) -> int:
        value = item.get("size", self._group.get("size", 0))
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def set_remove(self, path: str, remove: bool = True) -> bool:
        path = str(path)
        paths = [str(item["path"]) for item in self._copies]
        if path not in paths:
            return False
        if remove:
            if path not in self._removals:
                if len(self._removals) + 1 >= len(paths):
                    return False
                self._removals.add(path)
        else:
            self._removals.discard(path)
        return True

    def toggle_remove(self, path: str) -> bool:
        path = str(path)
        return self.set_remove(path, path not in self._removals)

    def keep_only(self, path: str) -> bool:
        path = str(path)
        paths = [str(item["path"]) for item in self._copies]
        if path not in paths:
            return False
        self._removals = {item for item in paths if item != path}
        return True

    def reset(self):
        self._removals.clear()

    def keep_newest(self) -> Optional[str]:
        return self._keep_by_timestamp(newest=True)

    def keep_oldest(self) -> Optional[str]:
        return self._keep_by_timestamp(newest=False)

    def keep_shortest_path(self) -> Optional[str]:
        if not self._copies:
            return None
        chosen = min(self._copies, key=_path_sort_key)
        self.keep_only(str(chosen["path"]))
        return str(chosen["path"])

    def _keep_by_timestamp(self, newest: bool) -> Optional[str]:
        if not self._copies:
            return None
        dated = [
            (item, _parse_modified(item.get("modified")))
            for item in self._copies
        ]
        dated = [(item, stamp) for item, stamp in dated if stamp is not None]
        if dated:
            target = (
                max(stamp for _, stamp in dated)
                if newest
                else min(stamp for _, stamp in dated)
            )
            candidates = [
                item for item, stamp in dated if stamp == target
            ]
        else:
            candidates = self._copies
        chosen = min(candidates, key=_path_sort_key)
        self.keep_only(str(chosen["path"]))
        return str(chosen["path"])


class DuplicateReviewWidget(QWidget):
    """Group list plus explicit per-copy keep/remove selection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._groups: List[Dict[str, Any]] = []
        self._selections: Dict[int, DuplicateSelection] = {}
        self._current_index = None
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(6)
        self.group_filter_input = QLineEdit()
        self.group_filter_input.setPlaceholderText(
            "Filter duplicate groups by filename or path"
        )
        self.group_filter_input.setClearButtonEnabled(True)
        filter_layout.addWidget(self.group_filter_input, 1)
        self.group_filter_status = QLabel("")
        self.group_filter_status.setStyleSheet(
            "color: #6b7280; font-size: 11px;"
        )
        filter_layout.addWidget(self.group_filter_status)
        layout.addLayout(filter_layout)

        self.group_model = RecordTableModel(
            [
                ColumnSpec(
                    "Name",
                    lambda group: group.get("_name", ""),
                    lambda group: str(group.get("_name", "")).casefold(),
                ),
                ColumnSpec(
                    "Size",
                    lambda group: _format_size(group.get("size", 0)),
                    lambda group: int(group.get("size") or 0),
                ),
                ColumnSpec(
                    "Copies",
                    lambda group: str(len(group.get("files", []))),
                    lambda group: len(group.get("files", [])),
                ),
                ColumnSpec(
                    "Potential Savings",
                    lambda group: _format_size(
                        group.get("potential_savings", 0)
                    ),
                    lambda group: int(
                        group.get("potential_savings") or 0
                    ),
                ),
            ],
            [],
            search_fields=("_name", "_search_text"),
        )
        self.group_proxy = RecordFilterProxyModel()
        self.group_proxy.setSourceModel(self.group_model)
        self.group_table = RecordTableView()
        self.group_table.setModel(self.group_proxy)
        self.group_table.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        self.group_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.group_table.setMaximumHeight(150)
        self.group_table.itemSelectionChanged.connect(
            self._on_group_selected
        )
        self.group_filter_input.textChanged.connect(
            self._on_group_filter_changed
        )
        layout.addWidget(self.group_table)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.keep_newest_button = QPushButton("Keep newest")
        self.keep_oldest_button = QPushButton("Keep oldest")
        self.keep_shortest_button = QPushButton("Keep shortest path")
        for button in (
            self.keep_newest_button,
            self.keep_oldest_button,
            self.keep_shortest_button,
        ):
            button.setStyleSheet(
                "padding: 6px 10px; border-radius: 6px; "
                "background-color: #f3f4f6; color: #111827; "
                "border: 1px solid #d1d5db;"
            )
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        self.keep_newest_button.clicked.connect(self._keep_newest)
        self.keep_oldest_button.clicked.connect(self._keep_oldest)
        self.keep_shortest_button.clicked.connect(self._keep_shortest)

        self.copy_table = QTableWidget(0, 5)
        self.copy_table.setHorizontalHeaderLabels(
            ["Path", "Size", "Modified", "Folder", "Remove"]
        )
        self.copy_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.copy_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.copy_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.copy_table.setWordWrap(False)
        self.copy_table.verticalHeader().setVisible(False)
        self.copy_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.copy_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.copy_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.copy_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch
        )
        self.copy_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeToContents
        )
        self.copy_table.itemChanged.connect(self._on_copy_item_changed)
        layout.addWidget(self.copy_table, 1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #374151; font-size: 12px;")
        layout.addWidget(self.status_label)
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(self.summary_label)
        self._update_buttons()

    @property
    def group_count(self) -> int:
        return len(self._groups)

    @property
    def current_selection(self) -> Optional[DuplicateSelection]:
        if self._current_index is None:
            return None
        return self._selections.get(self._current_index)

    @property
    def removal_paths(self) -> List[str]:
        selection = self.current_selection
        return selection.removal_paths if selection else []

    @property
    def removal_sizes(self) -> Dict[str, int]:
        selection = self.current_selection
        return selection.removal_sizes if selection else {}

    def set_groups(self, groups):
        self._groups = []
        self._selections = {}
        self._current_index = None
        for raw_group in groups or []:
            if not isinstance(raw_group, dict):
                continue
            copies = []
            seen = set()
            for item in raw_group.get("files", []) or []:
                if not isinstance(item, dict):
                    continue
                path = item.get("path")
                if not isinstance(path, str) or not path or path in seen:
                    continue
                seen.add(path)
                copies.append(dict(item))
            if len(copies) < 2:
                continue
            group = dict(raw_group)
            group["files"] = copies
            group["_name"] = _group_name(group)
            group["_search_text"] = _group_search_text(group)
            self._groups.append(group)

        self._current_index = None
        self.group_model.set_records(self._groups)
        self._update_group_filter_status()
        self._select_first_visible_group()

    def select_group(self, row: int):
        if not (0 <= row < len(self._groups)):
            return
        source_index = self.group_model.index(row, 0)
        proxy_index = self.group_proxy.mapFromSource(source_index)
        if not proxy_index.isValid() and self.group_filter_input.text():
            self.group_filter_input.clear()
            proxy_index = self.group_proxy.mapFromSource(source_index)
        if not proxy_index.isValid():
            return
        self._loading = True
        try:
            self.group_table.setCurrentIndex(proxy_index)
            self.group_table.selectRow(proxy_index.row())
        finally:
            self._loading = False
        self._load_group(row)

    def _select_first_visible_group(self):
        if self.group_proxy.rowCount() <= 0:
            self._current_index = None
            self._load_group(-1)
            self._update_group_filter_status()
            return
        self._loading = True
        try:
            self.group_table.setCurrentIndex(self.group_proxy.index(0, 0))
            self.group_table.selectRow(0)
        finally:
            self._loading = False
        source_index = self.group_proxy.mapToSource(
            self.group_proxy.index(0, 0)
        )
        self._load_group(source_index.row())

    def _on_group_filter_changed(self, _text):
        self.group_proxy.set_search_text(self.group_filter_input.text())
        self._update_group_filter_status()
        if self._current_index is not None:
            source_index = self.group_model.index(
                self._current_index, 0
            )
            proxy_index = self.group_proxy.mapFromSource(source_index)
            if proxy_index.isValid():
                self._loading = True
                try:
                    self.group_table.setCurrentIndex(proxy_index)
                    self.group_table.selectRow(proxy_index.row())
                finally:
                    self._loading = False
                return
        self._select_first_visible_group()

    def _update_group_filter_status(self):
        active = bool(self.group_filter_input.text().strip())
        total = self.group_model.rowCount()
        visible = self.group_proxy.rowCount()
        if not active:
            self.group_filter_status.setText("")
        elif visible == 0:
            self.group_filter_status.setText(
                "No duplicate groups match the current filter."
            )
        else:
            self.group_filter_status.setText(
                f"Showing {visible} of {total} groups."
            )

    def refresh_current_selection(self):
        selection = self.current_selection
        self.copy_table.blockSignals(True)
        try:
            for row in range(self.copy_table.rowCount()):
                item = self.copy_table.item(row, 4)
                if item is None:
                    continue
                path = item.data(Qt.UserRole)
                item.setCheckState(
                    Qt.Checked
                    if selection
                    and path in selection.removal_paths
                    else Qt.Unchecked
                )
        finally:
            self.copy_table.blockSignals(False)
        self._update_summary()

    def _load_group(self, row):
        self._loading = True
        self.status_label.setText("")
        self.copy_table.setRowCount(0)
        if not (0 <= row < len(self._groups)):
            self._current_index = None
            self._loading = False
            self._update_summary()
            self._update_buttons()
            return

        self._current_index = row
        selection = self._selections.get(row)
        if selection is None:
            selection = DuplicateSelection(self._groups[row])
            self._selections[row] = selection

        for copy_row, item in enumerate(selection.copies):
            path = str(item.get("path", ""))
            self.copy_table.insertRow(copy_row)
            values = [
                path,
                _format_size(item.get("size", 0)),
                item.get("modified") or "Unknown",
                item.get("directory")
                or os.path.dirname(path)
                or "Unknown",
                "",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setToolTip(path)
                self.copy_table.setItem(copy_row, column, cell)
            check = QTableWidgetItem("")
            check.setFlags(
                Qt.ItemIsUserCheckable
                | Qt.ItemIsEnabled
                | Qt.ItemIsSelectable
            )
            check.setData(Qt.UserRole, path)
            check.setCheckState(
                Qt.Checked
                if path in selection.removal_paths
                else Qt.Unchecked
            )
            self.copy_table.setItem(copy_row, 4, check)

        self._loading = False
        self._update_summary()
        self._update_buttons()

    def _on_group_selected(self):
        if self._loading:
            return
        index = self.group_table.currentIndex()
        if not index.isValid():
            self._current_index = None
            self._load_group(-1)
            return
        source_index = self.group_proxy.mapToSource(index)
        if source_index.isValid():
            self._load_group(source_index.row())
        else:
            self._current_index = None
            self._load_group(-1)

    def _on_copy_item_changed(self, item):
        if self._loading or item.column() != 4:
            return
        selection = self.current_selection
        if selection is None:
            return
        path = item.data(Qt.UserRole)
        checked = item.checkState() == Qt.Checked
        if not selection.set_remove(path, checked):
            self.copy_table.blockSignals(True)
            item.setCheckState(Qt.Unchecked)
            self.copy_table.blockSignals(False)
            self.status_label.setText("At least one copy must remain.")
        self._update_summary()

    def _keep_newest(self):
        self._apply_keep("newest")

    def _keep_oldest(self):
        self._apply_keep("oldest")

    def _keep_shortest(self):
        self._apply_keep("shortest")

    def _apply_keep(self, strategy):
        selection = self.current_selection
        if selection is None:
            return
        if strategy == "newest":
            path = selection.keep_newest()
        elif strategy == "oldest":
            path = selection.keep_oldest()
        else:
            path = selection.keep_shortest_path()
        self.refresh_current_selection()
        if path:
            self.status_label.setText(f"Keeping: {path}")

    def _update_summary(self):
        selection = self.current_selection
        if selection is None:
            self.summary_label.setText("No duplicate groups.")
            self.status_label.setText("")
            return
        self.summary_label.setText(
            f"Keeping {len(selection.retained_paths)} of "
            f"{len(selection.copies)} copies | "
            f"Removing {selection.removal_count} | "
            f"Estimated savings: {_format_size(selection.savings)}"
        )

    def _update_buttons(self):
        enabled = self.current_selection is not None
        for button in (
            self.keep_newest_button,
            self.keep_oldest_button,
            self.keep_shortest_button,
        ):
            button.setEnabled(enabled)
