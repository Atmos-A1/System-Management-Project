from types import SimpleNamespace

from panther.services import process_adapter


class FakeNoSuchProcess(Exception): pass
class FakeAccessDenied(Exception): pass
class FakeZombieProcess(Exception): pass


class FakePsutil:
    NoSuchProcess = FakeNoSuchProcess
    AccessDenied = FakeAccessDenied
    ZombieProcess = FakeZombieProcess
    def __init__(self, processes): self.processes = processes
    def process_iter(self, attrs):
        self.attrs = attrs
        return iter(self.processes)


class FakeProcess:
    def __init__(self, pid):
        self.info = {
            "pid": pid, "name": "process-{}.exe".format(pid),
            "create_time": 100.0 + pid,
            "cpu_times": SimpleNamespace(user=1.0, system=0.1),
            "memory_info": SimpleNamespace(rss=1024, vms=2048),
            "ppid": 1, "exe": None, "username": None,
            "status": "running", "num_threads": 2,
        }


def test_iter_process_records_yields_typed_records_incrementally(monkeypatch):
    fake = FakePsutil([FakeProcess(1), FakeProcess(2), FakeProcess(3)])
    monkeypatch.setattr(process_adapter, "psutil", fake)
    records = process_adapter.iter_process_records()
    assert next(records).identity.pid == 1
    assert "cmdline" not in fake.attrs
    assert next(records).identity.pid == 2
    assert next(records).identity.pid == 3


def test_get_process_records_still_returns_complete_list(monkeypatch):
    monkeypatch.setattr(process_adapter, "psutil", FakePsutil([FakeProcess(5), FakeProcess(6)]))
    records = process_adapter.get_process_records()
    assert [record.identity.pid for record in records] == [5, 6]
