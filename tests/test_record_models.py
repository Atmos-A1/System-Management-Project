"""Tests for the shared record table model and proxy filtering."""

import time

from PySide6.QtCore import Qt

from panther.ui.table_models import (
    ColumnSpec,
    RecordFilterProxyModel,
    RecordTableModel,
    format_size,
)


def _record(name, path, size, modified="2024-01-01 00:00:00"):
    return {
        "name": name,
        "path": path,
        "size": size,
        "modified": modified,
    }


def _columns():
    return [
        ColumnSpec(
            "Name",
            lambda item: item["name"],
            lambda item: str(item["name"]).casefold(),
        ),
        ColumnSpec(
            "Path",
            lambda item: item["path"],
            lambda item: str(item["path"]).casefold(),
        ),
        ColumnSpec(
            "Size",
            lambda item: format_size(item["size"]),
            lambda item: int(item["size"]),
        ),
        ColumnSpec(
            "Modified",
            lambda item: item["modified"],
            lambda item: str(item["modified"]),
        ),
    ]


def _records():
    return [
        _record("alpha.txt", "/data/alpha.txt", 100),
        _record("beta.log", "/other/beta.log", 300),
        _record("Gamma.txt", "/data/gamma.txt", 200),
    ]


def test_rows_columns_display_and_roles():
    records = _records()
    model = RecordTableModel(_columns(), records, search_fields=("name", "path"))

    assert model.rowCount() == 3
    assert model.columnCount() == 4
    assert model.headerData(0, Qt.Horizontal) == "Name"
    assert model.index(0, 0).data(Qt.DisplayRole) == "alpha.txt"
    assert model.index(0, 2).data(Qt.DisplayRole) == "100 B"
    assert model.index(0, 0).data(Qt.UserRole)["path"] == "/data/alpha.txt"
    assert model.record_at(1)["name"] == "beta.log"


def test_filtering_is_case_insensitive_by_name_and_path():
    model = RecordTableModel(_columns(), _records(), search_fields=("name", "path"))
    proxy = RecordFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.set_search_text("ALPHA")
    assert proxy.rowCount() == 1
    assert proxy.index(0, 0).data() == "alpha.txt"

    proxy.set_search_text("other/")
    assert proxy.rowCount() == 1
    assert proxy.index(0, 0).data() == "beta.log"

    proxy.set_search_text("")
    assert proxy.rowCount() == 3


def test_empty_filter_result_and_empty_dataset():
    model = RecordTableModel(_columns(), _records(), search_fields=("name", "path"))
    proxy = RecordFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.set_search_text("does-not-exist")
    assert proxy.rowCount() == 0

    model.set_records([])
    assert model.rowCount() == 0
    assert proxy.rowCount() == 0


def test_sorting_preserves_source_record_identity():
    model = RecordTableModel(_columns(), _records(), search_fields=("name", "path"))
    proxy = RecordFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.sort(2, Qt.AscendingOrder)
    sizes = [
        proxy.index(row, 0).data(Qt.UserRole)["size"]
        for row in range(proxy.rowCount())
    ]
    assert sizes == [100, 200, 300]

    proxy.sort(0, Qt.DescendingOrder)
    names = [
        proxy.index(row, 0).data(Qt.UserRole)["name"]
        for row in range(proxy.rowCount())
    ]
    assert names == ["Gamma.txt", "beta.log", "alpha.txt"]

    proxy.set_search_text("txt")
    proxy.sort(2, Qt.DescendingOrder)
    visible = [
        proxy.index(row, 0).data(Qt.UserRole)["path"]
        for row in range(proxy.rowCount())
    ]
    assert visible == ["/data/gamma.txt", "/data/alpha.txt"]


def test_proxy_mapping_returns_original_record():
    records = _records()
    model = RecordTableModel(_columns(), records, search_fields=("name", "path"))
    proxy = RecordFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.sort(2, Qt.DescendingOrder)

    proxy_index = proxy.index(0, 0)
    source_index = proxy.mapToSource(proxy_index)
    assert source_index.row() == 1
    assert model.record_at(source_index.row()) is records[1]


def test_large_dataset_filter_sort_and_repeated_updates():
    records = [
        _record(
            f"file-{index:05d}.bin",
            f"/data/group-{index % 20}/file-{index:05d}.bin",
            index,
        )
        for index in range(3000)
    ]
    model = RecordTableModel(_columns(), records, search_fields=("name", "path"))
    proxy = RecordFilterProxyModel()
    proxy.setSourceModel(model)

    started = time.monotonic()
    for index in range(20):
        proxy.set_search_text(f"group-{index % 20}")
        assert proxy.rowCount() > 0
    proxy.set_search_text("")
    proxy.sort(2, Qt.DescendingOrder)
    assert proxy.rowCount() == 3000
    assert proxy.index(0, 0).data(Qt.UserRole)["size"] == 2999
    assert time.monotonic() - started < 5.0
