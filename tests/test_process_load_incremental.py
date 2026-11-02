import threading

from panther.domain.models import ProcessIdentity, ProcessRecord
from panther.ui.processes import ProcessLoadThread
from datetime import datetime, timezone


def make_record():
    return ProcessRecord(
        identity=ProcessIdentity(701, 123.0, "editor.exe", r"C:\Apps\editor.exe"),
        ppid=1, username="tester", status="running", cpu_percent=1.0,
        memory_rss=1024 * 1024, memory_vms=2 * 1024 * 1024,
        num_threads=2, first_seen=datetime.now(timezone.utc),
    )


def test_first_batch_is_classified_before_discovery_finishes(qtbot):
    release_loader = threading.Event()
    discovery_finished = threading.Event()
    observed = []

    def loader():
        yield make_record()
        release_loader.wait(2)
        discovery_finished.set()

    def classify(process):
        return {
            "category": "User application", "risk_level": "Review required",
            "confidence": 0.5, "explanation": "Candidate only",
            "evidence": [], "can_terminate": False,
        }

    thread = ProcessLoadThread(loader=loader, classifier=classify, batch_size=1)

    def receive_batch(batch):
        observed.extend(batch)
        assert batch[0][1]["category"] == "User application"
        assert not discovery_finished.is_set()
        release_loader.set()

    thread.batch_ready.connect(receive_batch)
    with qtbot.waitSignal(thread.completed, timeout=3000):
        thread.start()
    thread.wait()
    assert len(observed) == 1
