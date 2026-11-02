from types import SimpleNamespace

import pytest

from panther.services import process_adapter
from panther.services.process_adapter import get_process_records, get_processes


class FakeNoSuchProcess(Exception):
    pass


class FakeAccessDenied(Exception):
    pass


class FakeZombieProcess(Exception):
    pass


class FakePsutil:
    NoSuchProcess = FakeNoSuchProcess
    AccessDenied = FakeAccessDenied
    ZombieProcess = FakeZombieProcess

    def __init__(self, processes):
        self.processes = processes

    def process_iter(self, attrs):
        self.requested_attrs = attrs
        return iter(self.processes)


class DummyProcess:
    def __init__(self, pid, name, create_time=100.0, cpu_times=None,
                 memory_info=None, ppid=1, exe=None, username="tester",
                 status="running", num_threads=3):
        self.info = {
            "pid": pid,
            "name": name,
            "create_time": create_time,
            "cpu_times": cpu_times,
            "memory_info": memory_info,
            "ppid": ppid,
            "exe": exe,
            "username": username,
            "status": status,
            "num_threads": num_threads,
        }


def install_fake_psutil(monkeypatch, processes):
    fake = FakePsutil(processes)
    monkeypatch.setattr(process_adapter, "psutil", fake)
    return fake


def test_get_process_records_returns_typed_records(monkeypatch):
    memory = SimpleNamespace(rss=1024 * 1024, vms=2 * 1024 * 1024)
    install_fake_psutil(monkeypatch, [DummyProcess(12, "worker.exe", memory_info=memory)])

    records = get_process_records()

    assert len(records) == 1
    record = records[0]
    assert record.identity.pid == 12
    assert record.identity.create_time == 100.0
    assert record.identity.name == "worker.exe"
    assert record.memory_rss == 1024 * 1024
    assert record.memory_vms == 2 * 1024 * 1024
    assert record.cpu_percent is None


def test_missing_metrics_remain_none(monkeypatch):
    install_fake_psutil(monkeypatch, [DummyProcess(13, "partial.exe", memory_info=None)])

    record = get_process_records()[0]

    assert record.memory_rss is None
    assert record.memory_vms is None
    assert record.cpu_percent is None
    assert record.username == "tester"


def test_process_without_creation_time_is_skipped(monkeypatch):
    install_fake_psutil(monkeypatch, [DummyProcess(14, "no-start.exe", create_time=None)])
    assert get_process_records() == []


def test_one_inaccessible_process_does_not_hide_other_processes(monkeypatch):
    inaccessible = DummyProcess(15, "blocked.exe")

    class BrokenProcess:
        @property
        def info(self):
            raise FakeAccessDenied()

    install_fake_psutil(monkeypatch, [BrokenProcess(), inaccessible])
    records = get_process_records()
    assert [record.identity.pid for record in records] == [15]


def test_legacy_get_processes_preserves_dictionary_shape(monkeypatch):
    memory = SimpleNamespace(rss=4096, vms=8192)
    install_fake_psutil(monkeypatch, [DummyProcess(16, "legacy.exe", memory_info=memory)])

    processes = get_processes()

    assert isinstance(processes[0], dict)
    assert processes[0]["pid"] == 16
    assert processes[0]["name"] == "legacy.exe"
    assert processes[0]["cpu_percent"] == 0.0
    assert processes[0]["memory_rss"] == 4096
    assert "cmdline" in processes[0]
    assert "start_time" in processes[0]


def test_cpu_sampler_first_sample_is_unavailable_then_uses_delta(monkeypatch):
    sampler = process_adapter._CpuSampler()
    identity = process_adapter.ProcessIdentity(17, 100.0, "cpu.exe")
    first = SimpleNamespace(user=1.0, system=1.0)
    second = SimpleNamespace(user=2.0, system=1.0)

    assert sampler.sample(identity, first, sampled_at=10.0) is None
    assert sampler.sample(identity, second, sampled_at=12.0) == pytest.approx(50.0)


def test_cpu_sampler_does_not_reuse_sample_after_pid_reuse():
    sampler = process_adapter._CpuSampler()
    old_identity = process_adapter.ProcessIdentity(18, 100.0, "old.exe")
    new_identity = process_adapter.ProcessIdentity(18, 200.0, "new.exe")
    cpu = SimpleNamespace(user=2.0, system=0.0)

    assert sampler.sample(old_identity, cpu, sampled_at=1.0) is None
    assert sampler.sample(new_identity, cpu, sampled_at=2.0) is None
    assert len(sampler._samples) == 1
    assert new_identity.key in sampler._samples


def test_get_process_records_requires_psutil(monkeypatch):
    monkeypatch.setattr(process_adapter, "psutil", None)
    with pytest.raises(RuntimeError, match="psutil is required"):
        get_process_records()


def test_first_seen_is_stable_for_same_process_instance(monkeypatch):
    process = DummyProcess(19, "stable.exe")
    install_fake_psutil(monkeypatch, [process])

    first = get_process_records()[0].first_seen
    second = get_process_records()[0].first_seen

    assert first == second


def test_legacy_api_preserves_command_line(monkeypatch):
    process = DummyProcess(20, "legacy-cmd.exe")
    process.info["cmdline"] = ["legacy-cmd.exe", "--safe-test"]
    install_fake_psutil(monkeypatch, [process])

    record = get_processes()[0]

    assert record["cmdline"] == "legacy-cmd.exe --safe-test"
