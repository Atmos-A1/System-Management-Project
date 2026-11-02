import pytest

from panther.domain.models import ProcessIdentity
from panther.services.windows_process_adapter import (
    ProcessVerificationStatus,
    WindowsProcessAdapter,
)


class FakeBackend:
    def __init__(self, create_time=100.0, image_path=r"C:\Apps\demo.exe"):
        self.create_time = create_time
        self.image_path = image_path
        self.closed = []
        self.opened = []

    def open_process(self, pid):
        self.opened.append(pid)
        return {"pid": pid}

    def get_creation_time(self, handle):
        return self.create_time

    def get_image_path(self, handle):
        return self.image_path

    def close_handle(self, handle):
        self.closed.append(handle)


def identity(pid=1234, create_time=100.0):
    return ProcessIdentity(pid, create_time, "demo.exe", r"C:\Apps\demo.exe")


def test_inspect_verifies_matching_process_identity_and_closes_handle():
    backend = FakeBackend()
    result = WindowsProcessAdapter(backend).inspect(identity())

    assert result.status is ProcessVerificationStatus.VERIFIED
    assert result.verified
    assert result.observed_create_time == 100.0
    assert result.observed_image_path == r"C:\Apps\demo.exe"
    assert result.handle_closed
    assert backend.opened == [1234]
    assert len(backend.closed) == 1


def test_pid_reuse_is_reported_as_identity_mismatch():
    backend = FakeBackend(create_time=200.0)
    result = WindowsProcessAdapter(backend).inspect(identity(create_time=100.0))

    assert result.status is ProcessVerificationStatus.IDENTITY_MISMATCH
    assert not result.verified
    assert result.handle_closed


def test_creation_time_tolerance_is_configurable():
    backend = FakeBackend(create_time=100.01)
    result = WindowsProcessAdapter(backend, time_tolerance_seconds=0.02).inspect(identity())
    assert result.status is ProcessVerificationStatus.VERIFIED


def test_access_denied_is_not_reported_as_verified():
    class DeniedBackend(FakeBackend):
        def open_process(self, pid):
            raise PermissionError("access denied")

    result = WindowsProcessAdapter(DeniedBackend()).inspect(identity())
    assert result.status is ProcessVerificationStatus.ACCESS_DENIED
    assert not result.verified
    assert not result.handle_closed


def test_process_exit_is_reported_without_success():
    class GoneBackend(FakeBackend):
        def open_process(self, pid):
            raise ProcessLookupError("process exited")

    result = WindowsProcessAdapter(GoneBackend()).inspect(identity())
    assert result.status is ProcessVerificationStatus.ALREADY_EXITED
    assert not result.verified


def test_image_path_failure_does_not_replace_creation_time_identity():
    class NoImageBackend(FakeBackend):
        def get_image_path(self, handle):
            raise PermissionError("image path unavailable")

    result = WindowsProcessAdapter(NoImageBackend()).inspect(identity())
    assert result.status is ProcessVerificationStatus.VERIFIED
    assert result.observed_image_path is None
    assert result.handle_closed


def test_handle_is_closed_when_creation_time_query_fails():
    class BrokenBackend(FakeBackend):
        def get_creation_time(self, handle):
            raise OSError("query failed")

    backend = BrokenBackend()
    result = WindowsProcessAdapter(backend).inspect(identity())
    assert result.status is ProcessVerificationStatus.QUERY_FAILED
    assert not result.verified
    assert result.handle_closed
    assert len(backend.closed) == 1


def test_pid_zero_is_rejected_without_opening_handle():
    backend = FakeBackend()
    result = WindowsProcessAdapter(backend).inspect(identity(pid=0))

    assert result.status is ProcessVerificationStatus.UNSUPPORTED
    assert backend.opened == []
    assert backend.closed == []


def test_invalid_identity_type_is_rejected():
    with pytest.raises(TypeError):
        WindowsProcessAdapter(FakeBackend()).inspect({"pid": 1234})
