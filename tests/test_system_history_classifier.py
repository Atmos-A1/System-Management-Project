"""Tests for system_monitor defaults, history clearing and critical-process matching."""
import os
import sqlite3

import pytest

from panther.services import system_monitor
from panther.services.process_classifier import CRITICAL_PROCESSES, classify_process


# --- system_monitor ------------------------------------------------------

def test_disk_usage_default_path_works_on_this_platform():
    usage = system_monitor.get_disk_usage()
    assert usage["total"] > 0
    assert 0 <= usage["percent"] <= 100


def test_default_disk_path_uses_system_drive_on_windows(monkeypatch):
    monkeypatch.setattr(system_monitor.os, "name", "nt")
    monkeypatch.setenv("SystemDrive", "D:")
    assert system_monitor._default_disk_path() == "D:\\"
    monkeypatch.delenv("SystemDrive")
    assert system_monitor._default_disk_path() == "C:\\"


def test_cpu_percent_does_not_block(monkeypatch):
    seen = {}
    monkeypatch.setattr(system_monitor.psutil, "cpu_percent",
                        lambda interval=None: seen.setdefault("interval", interval) or 12.5)
    system_monitor.get_cpu_percent()
    assert seen["interval"] is None  # a blocking interval would freeze the UI thread


# --- history -------------------------------------------------------------

@pytest.fixture
def history(tmp_path, monkeypatch):
    """History service bound to a throwaway database."""
    from panther import db as db_module
    from panther.services import history as history_module

    temp_db = db_module.Database(tmp_path / "history_test.db")
    monkeypatch.setattr(history_module, "db", temp_db)
    history_module._ensure_schema()
    return history_module


def test_clear_history_removes_all_rows_and_reports_count(history):
    for i in range(3):
        history.record_event("action", "event {}".format(i))
    assert len(history.get_recent()) == 3
    assert history.clear_history() == 3
    assert history.get_recent() == []
    assert history.clear_history() == 0


def test_record_event_timestamp_is_naive_utc_iso(history):
    history.record_event("metric", "{}")
    ts = history.get_recent(1)[0][1]
    assert "T" in ts and "+" not in ts and not ts.endswith("Z")


# --- process classifier --------------------------------------------------

def test_critical_process_names_are_lowercase_so_matching_works():
    assert all(name == name.lower() for name in CRITICAL_PROCESSES)


@pytest.mark.parametrize("name", ["RuntimeBroker.exe", "SearchIndexer.exe", "svchost.exe"])
def test_mixed_case_critical_processes_are_protected(name):
    result = classify_process({"name": name, "exe": r"C:\Windows\System32\{}".format(name)})
    assert result["category"] == "Critical system component"
    assert result["can_terminate"] is False


def test_unknown_process_is_never_terminable():
    result = classify_process({"name": "mystery.exe", "exe": ""})
    assert result["category"] == "Unknown / unverified"
    assert result["can_terminate"] is False
