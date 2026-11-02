"""Background scan controller for the Storage screen.

A scan worker owns its own scanner/detector instances and runs directory
enumeration and duplicate hashing on a QThread. Results are tagged with a
generation so late signals from an older scan cannot update the UI.

Worker objects live in the GUI thread; only their ``run`` method executes in
the scan thread. This keeps object destruction and Qt signal delivery on the
GUI thread. Active threads are held in a module-level registry so destroying a
screen cannot destroy a running QThread.
"""

import threading
import time
import traceback

from PySide6.QtCore import QCoreApplication, QObject, QThread, Qt, Signal

from ..services.duplicate_detector import DuplicateDetector
from ..services.file_scanner import FileScanner


# Keep running threads alive even if their owning screen is destroyed. They
# remove themselves when their run() method returns.
_ACTIVE_THREADS = set()


class ScanWorker(QObject):
    progress = Signal(dict)
    finished = Signal(dict)
    cancelled = Signal(dict)
    failed = Signal(dict)

    def __init__(
        self,
        generation,
        kind,
        root_path,
        max_depth,
        include_hidden=False,
        parent=None,
    ):
        super().__init__(parent)
        self.generation = generation
        self.kind = kind
        self.root_path = root_path
        self.max_depth = max_depth
        self.include_hidden = include_hidden
        self._cancel_event = threading.Event()
        self._errors = []
        self._last_scan_progress = {}
        self._last_progress_emit = 0.0

    def request_cancel(self):
        self._cancel_event.set()

    def run(self):
        started_at = time.monotonic()
        scanner = FileScanner()
        detector = DuplicateDetector()

        try:
            files = scanner.scan_directory(
                self.root_path,
                max_depth=self.max_depth,
                include_hidden=self.include_hidden,
                cancel_event=self._cancel_event,
                progress_callback=self._on_scan_progress,
                error_callback=self._record_error,
            )

            if self._cancel_event.is_set() or scanner.cancelled:
                self.cancelled.emit(self._cancel_payload())
                return

            largest = []
            duplicates = []
            if self.kind == "largest":
                largest = scanner.get_largest_files(files, 200)
            else:
                self._last_progress_emit = 0.0
                duplicates = detector.find_duplicates(
                    files,
                    cancel_event=self._cancel_event,
                    progress_callback=self._on_hash_progress,
                    error_callback=self._record_error,
                )
                if self._cancel_event.is_set() or detector.cancelled:
                    self.cancelled.emit(self._cancel_payload())
                    return

            payload = {
                "generation": self.generation,
                "kind": self.kind,
                "root": self.root_path,
                "files": files,
                "largest": largest,
                "duplicates": duplicates,
                "errors": list(self._errors),
                "partial": bool(self._errors),
                "files_scanned": len(files),
                "directories_scanned": self._last_scan_progress.get(
                    "directories_scanned", 0
                ),
                "bytes_scanned": self._last_scan_progress.get(
                    "bytes_scanned", 0
                ),
                "elapsed_seconds": time.monotonic() - started_at,
            }
            self.finished.emit(payload)
        except Exception as exc:
            self.failed.emit(
                {
                    "generation": self.generation,
                    "kind": self.kind,
                    "root": self.root_path,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )

    def _cancel_payload(self):
        return {
            "generation": self.generation,
            "kind": self.kind,
            "root": self.root_path,
            "errors": list(self._errors),
        }

    def _on_scan_progress(self, progress):
        self._last_scan_progress = progress
        if not self._should_emit_progress():
            return
        payload = dict(progress)
        payload.update(
            {
                "generation": self.generation,
                "kind": self.kind,
                "phase": "scan",
            }
        )
        self.progress.emit(payload)

    def _on_hash_progress(self, progress):
        if not self._should_emit_progress():
            return
        payload = dict(progress)
        payload.update(
            {
                "generation": self.generation,
                "kind": self.kind,
                "phase": "hash",
            }
        )
        self.progress.emit(payload)

    def _should_emit_progress(self):
        now = time.monotonic()
        if (
            self._last_progress_emit == 0.0
            or now - self._last_progress_emit >= 0.1
        ):
            self._last_progress_emit = now
            return True
        return False

    def _record_error(self, error):
        self._errors.append(error)


class _ScanThread(QThread):
    """Thread whose only job is to execute one worker."""

    def __init__(self, worker):
        super().__init__()
        self.worker = worker

    def run(self):
        self.worker.run()


class ScanController(QObject):
    started = Signal(str)
    progress = Signal(dict)
    finished = Signal(dict)
    cancelled = Signal(dict)
    failed = Signal(dict)
    state_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._worker = None
        self._generation = 0

        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    @property
    def generation(self):
        return self._generation

    @property
    def is_running(self):
        return self._thread is not None

    def start(self, kind, root_path, max_depth, include_hidden=False):
        if kind not in {"largest", "duplicates"}:
            raise ValueError("kind must be 'largest' or 'duplicates'")
        if self._thread is not None:
            return False

        self._generation += 1
        generation = self._generation
        worker = ScanWorker(
            generation,
            kind,
            str(root_path),
            max_depth,
            include_hidden,
        )
        thread = _ScanThread(worker)

        # Queued connections guarantee controller handlers and therefore UI
        # signals run on the controller's GUI thread.
        worker.progress.connect(
            self._handle_progress, Qt.QueuedConnection
        )
        worker.finished.connect(
            self._handle_finished, Qt.QueuedConnection
        )
        worker.cancelled.connect(
            self._handle_cancelled, Qt.QueuedConnection
        )
        worker.failed.connect(
            self._handle_failed, Qt.QueuedConnection
        )

        thread.finished.connect(self._on_thread_finished)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda t=thread: _ACTIVE_THREADS.discard(t)
        )

        _ACTIVE_THREADS.add(thread)
        self._thread = thread
        self._worker = worker
        self.state_changed.emit(True)
        self.started.emit(kind)
        thread.start()
        return True

    def cancel(self):
        if self._worker is not None:
            self._worker.request_cancel()

    def shutdown(self, timeout_ms=5000):
        """Cancel and wait for the worker, bounded by ``timeout_ms``.

        Returns True when the thread has finished and the controller is ready.
        If the timeout expires, the controller remains busy and the thread is
        kept alive in the module registry; it is never destroyed while
        running.
        """
        thread = self._thread
        if thread is None:
            return True

        self.cancel()
        if not thread.wait(timeout_ms):
            return False

        self._finish_thread(thread)
        return True

    def _finish_thread(self, thread):
        if self._thread is not thread:
            return
        self._thread = None
        self._worker = None
        self.state_changed.emit(False)

    def _handle_progress(self, payload):
        if payload.get("generation") != self._generation:
            return
        self.progress.emit(payload)

    def _handle_finished(self, payload):
        if payload.get("generation") != self._generation:
            return
        self.finished.emit(payload)

    def _handle_cancelled(self, payload):
        if payload.get("generation") != self._generation:
            return
        self.cancelled.emit(payload)

    def _handle_failed(self, payload):
        if payload.get("generation") != self._generation:
            return
        self.failed.emit(payload)

    def _on_thread_finished(self):
        thread = self.sender()
        self._finish_thread(thread)
