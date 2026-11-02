import pytest
from panther.services.process_adapter import get_processes


def test_get_processes(monkeypatch):
    # Mock psutil.process_iter to return a deterministic list
    class DummyProc:
        def __init__(self, pid, name, cpu, rss):
            self.info = {
                "pid": pid,
                "name": name,
                "cpu_percent": cpu,
                "memory_info": type("mem", (), {"rss": rss})(),
                "ppid": 1,
                "exe": None,
                "cmdline": [],
                "username": None,
                "create_time": None,
                "status": "running",
            }

    dummy_list = [DummyProc(1, "procA", 0.0, 1024 * 1024), DummyProc(2, "procB", 5.5, 2 * 1024 * 1024)]

    class DummyPsutil:
        @staticmethod
        def process_iter(attrs):
            return dummy_list

    monkeypatch.setattr('panther.services.process_adapter.psutil', DummyPsutil)
    procs = get_processes()
    assert len(procs) == 2
    assert procs[0]["pid"] == 1
    assert procs[0]["name"] == "procA"
    assert procs[0]["cpu_percent"] == 0.0
    assert procs[0]["memory_rss"] == 1024 * 1024
