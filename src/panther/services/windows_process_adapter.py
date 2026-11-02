"""Read-only Windows process-instance verification.

This adapter opens a limited-information process handle, reads the process
creation time and image path, compares the creation time with the requested
ProcessIdentity, and closes the handle before returning. It does not expose
process-control operations.
"""

from dataclasses import dataclass
from enum import Enum
import os
from typing import Optional

from ..domain.models import ProcessIdentity


class ProcessVerificationStatus(str, Enum):
    VERIFIED = "verified"
    IDENTITY_MISMATCH = "identity_mismatch"
    ALREADY_EXITED = "already_exited"
    ACCESS_DENIED = "access_denied"
    UNSUPPORTED = "unsupported"
    QUERY_FAILED = "query_failed"


@dataclass(frozen=True)
class ProcessVerificationResult:
    status: ProcessVerificationStatus
    requested_identity: ProcessIdentity
    observed_create_time: Optional[float] = None
    observed_image_path: Optional[str] = None
    handle_closed: bool = False
    detail: str = ""

    @property
    def verified(self) -> bool:
        return self.status is ProcessVerificationStatus.VERIFIED


class _WindowsProcessApi:
    """Small ctypes wrapper around documented, query-only Windows APIs."""

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    ERROR_ACCESS_DENIED = 5
    ERROR_INVALID_PARAMETER = 87
    ERROR_NOT_FOUND = 1168
    FILETIME_EPOCH_OFFSET = 116444736000000000
    TICKS_PER_SECOND = 10000000

    def __init__(self):
        if os.name != "nt":
            raise OSError("Windows process inspection is available only on Windows")
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL
        self.kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        self.kernel32.GetProcessTimes.restype = wintypes.BOOL
        self.kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

    def open_process(self, pid):
        handle = self.kernel32.OpenProcess(
            self.PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            raise self._last_error("OpenProcess")
        return handle

    def get_creation_time(self, handle):
        c = self.ctypes
        w = self.wintypes
        created, exited, kernel, user = w.FILETIME(), w.FILETIME(), w.FILETIME(), w.FILETIME()
        ok = self.kernel32.GetProcessTimes(
            handle, c.byref(created), c.byref(exited), c.byref(kernel), c.byref(user)
        )
        if not ok:
            raise self._last_error("GetProcessTimes")
        ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
        return (ticks - self.FILETIME_EPOCH_OFFSET) / self.TICKS_PER_SECOND

    def get_image_path(self, handle):
        buffer = self.ctypes.create_unicode_buffer(32768)
        size = self.wintypes.DWORD(len(buffer))
        ok = self.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, self.ctypes.byref(size))
        if not ok:
            raise self._last_error("QueryFullProcessImageNameW")
        return buffer.value

    def close_handle(self, handle):
        if not self.kernel32.CloseHandle(handle):
            raise self._last_error("CloseHandle")

    def _last_error(self, operation):
        error = self.ctypes.get_last_error()
        return OSError(error, "{} failed (Windows error {})".format(operation, error))


class WindowsProcessAdapter:
    """Verify a process instance using a limited-information Windows handle.

    A backend can be injected for deterministic unit tests. The default backend
    is constructed lazily so importing this module is safe on non-Windows hosts.
    """

    def __init__(self, backend=None, time_tolerance_seconds=0.02):
        if time_tolerance_seconds < 0:
            raise ValueError("time_tolerance_seconds cannot be negative")
        self._backend = backend
        self._time_tolerance = float(time_tolerance_seconds)

    def _get_backend(self):
        if self._backend is None:
            self._backend = _WindowsProcessApi()
        return self._backend

    def inspect(self, identity: ProcessIdentity) -> ProcessVerificationResult:
        if not isinstance(identity, ProcessIdentity):
            raise TypeError("identity must be a ProcessIdentity")
        if identity.pid == 0:
            return ProcessVerificationResult(
                ProcessVerificationStatus.UNSUPPORTED, identity,
                detail="PID 0 is a system idle pseudo-process and cannot be opened normally.",
            )

        try:
            backend = self._get_backend()
        except (OSError, AttributeError) as exc:
            return ProcessVerificationResult(
                ProcessVerificationStatus.UNSUPPORTED, identity, detail=str(exc)
            )

        handle = None
        handle_closed = False
        observed_time = None
        image_path = None
        status = ProcessVerificationStatus.QUERY_FAILED
        detail = ""
        try:
            handle = backend.open_process(identity.pid)
            observed_time = float(backend.get_creation_time(handle))
            try:
                image_path = backend.get_image_path(handle)
            except (OSError, PermissionError):
                # Image path is supporting metadata, not the identity key.
                image_path = None

            if abs(observed_time - identity.create_time) > self._time_tolerance:
                status = ProcessVerificationStatus.IDENTITY_MISMATCH
                detail = "The PID now refers to a different process instance."
            else:
                status = ProcessVerificationStatus.VERIFIED
                detail = "PID and creation time match the requested process instance."
        except PermissionError as exc:
            status = ProcessVerificationStatus.ACCESS_DENIED
            detail = str(exc)
        except ProcessLookupError as exc:
            status = ProcessVerificationStatus.ALREADY_EXITED
            detail = str(exc)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 5 or getattr(exc, "errno", None) == 5:
                status = ProcessVerificationStatus.ACCESS_DENIED
            elif getattr(exc, "winerror", None) in (87, 1168) or getattr(exc, "errno", None) == 3:
                status = ProcessVerificationStatus.ALREADY_EXITED
            else:
                status = ProcessVerificationStatus.QUERY_FAILED
            detail = str(exc)
        except (TypeError, ValueError) as exc:
            status = ProcessVerificationStatus.QUERY_FAILED
            detail = str(exc)
        finally:
            if handle is not None:
                try:
                    backend.close_handle(handle)
                    handle_closed = True
                except OSError as exc:
                    status = ProcessVerificationStatus.QUERY_FAILED
                    detail = "Could not close process handle: {}".format(exc)

        return ProcessVerificationResult(
            status=status,
            requested_identity=identity,
            observed_create_time=observed_time,
            observed_image_path=image_path,
            handle_closed=handle_closed,
            detail=detail,
        )
