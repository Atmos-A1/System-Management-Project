"""Tests for the DataTable wrapper around the existing record table stack."""

import sys

import pytest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
)

from panther.ui.components.data_table import DataTable
from panther.ui.table_models import (
    ColumnSpec,
    RecordFilterProxyModel,
    RecordTableModel,
    RecordTableView,
)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication(sys.argv)
    yield application


def _model():
    columns = [
        ColumnSpec("Name", lambda record: record["name"]),
        ColumnSpec("Size", lambda record: record["size"]),
        ColumnSpec("Category", lambda record: record["category"]),
        ColumnSpec("Owner", lambda record: record["owner"]),
    ]
    records = [
        {"name": "Alpha", "size": "10 MB", "category": "Cache", "owner": "alice"},
        {"name": "Beta", "size": "20 MB", "category": "Logs", "owner": "bob"},
    ]
    return RecordTableModel(columns, records, search_fields=("name", "category"))


def test_data_table_preserves_record_table_view_behaviour(app):
    table = DataTable()

    assert isinstance(table, RecordTableView)
    assert table.objectName() == "dataTable"
    assert table.selectionBehavior() == QAbstractItemView.SelectRows
    assert table.selectionMode() == QAbstractItemView.SingleSelection
    assert table.editTriggers() == QAbstractItemView.NoEditTriggers
    assert table.alternatingRowColors() is True
    assert table.isSortingEnabled() is True
    assert table.verticalHeader().isHidden() is True


def test_data_table_works_with_existing_model_and_proxy(app):
    source = _model()
    proxy = RecordFilterProxyModel()
    proxy.setSourceModel(source)
    table = DataTable()
    table.setModel(proxy)

    assert table.rowCount() == 2
    assert [record["name"] for record in table.visible_records()] == ["Alpha", "Beta"]

    proxy.set_search_text("alpha")

    assert table.rowCount() == 1
    assert table.visible_records()[0]["name"] == "Alpha"


def test_data_table_selection_helpers_are_preserved(app):
    proxy = RecordFilterProxyModel()
    proxy.setSourceModel(_model())
    table = DataTable()
    table.setModel(proxy)
    table.setCurrentCell(1, 0)

    assert table.currentRow() == 1
    assert table.item(0, 0).text() == "Alpha"
    assert table.selected_records()[0]["name"] == "Beta"


def test_data_table_configure_columns_sets_resize_modes(app):
    proxy = RecordFilterProxyModel()
    proxy.setSourceModel(_model())
    table = DataTable()
    table.setModel(proxy)

    table.configure_columns(
        stretch=(0,), resize_to_contents=(1, 2), hidden=(3,)
    )

    header = table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.Stretch
    assert header.sectionResizeMode(1) == QHeaderView.ResizeToContents
    assert header.sectionResizeMode(2) == QHeaderView.ResizeToContents
    assert table.isColumnHidden(3)


def test_data_table_applies_configuration_when_model_is_set_later(app):
    table = DataTable()
    table.configure_columns(
        stretch=(0,), resize_to_contents=(1, 2), hidden=(3,)
    )

    proxy = RecordFilterProxyModel()
    proxy.setSourceModel(_model())
    table.setModel(proxy)

    header = table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.Stretch
    assert header.sectionResizeMode(1) == QHeaderView.ResizeToContents
    assert header.sectionResizeMode(2) == QHeaderView.ResizeToContents
    assert table.isColumnHidden(3)


def test_data_table_starts_ready_with_a_hidden_state_overlay(app):
    table = DataTable()

    assert table.state == "ready"
    assert table.state_overlay.isHidden()


def test_data_table_empty_state_shows_a_message_overlay(app):
    table = DataTable()

    table.set_state("empty", "No user-application candidates were found")

    assert table.state == "empty"
    assert table.state_overlay.isHidden() is False
    assert table.empty_state.title_label.text() == (
        "No user-application candidates were found"
    )


def test_data_table_loading_and_error_states_are_available(app):
    table = DataTable()

    table.set_state("loading", "Scanning…")
    assert table.state == "loading"
    assert table.loading_state.is_running is True
    assert table.loading_state.message_label.text() == "Scanning…"

    retries = []
    table.set_state("error", "Scan failed")
    table.error_state.retry_requested.connect(lambda: retries.append(True))
    assert table.error_state.title_label.text() == "Scan failed"
    assert table.error_state.retry_button.isHidden() is False

    table.set_state("ready")
    assert table.state_overlay.isHidden() is True


def test_data_table_rejects_unknown_state(app):
    table = DataTable()

    with pytest.raises(ValueError):
        table.set_state("sepia", "nope")


def test_data_table_numeric_columns_are_machine_readable(app):
    proxy = RecordFilterProxyModel()
    proxy.setSourceModel(_model())
    table = DataTable()
    table.setModel(proxy)

    table.configure_columns(stretch=(0,), numeric=(1,))

    assert table.numeric_columns() == (1,)
    # A right-aligning delegate is installed for the numeric column only.
    assert table.itemDelegateForColumn(1) is not None
    assert table.itemDelegateForColumn(0) is None
