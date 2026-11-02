"""Identity-bound, graceful-only Windows process closure.

The action handle is opened with query and wait rights only. Panther sends
WM_CLOSE to visible top-level windows and waits for process exit; it never
calls TerminateProcess or escalates automatically.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Any, Mapping, Optional

from ..domain.models import (
    ProcessActionRequest, ProcessActionResult, ProcessActionStatus,
    ProcessActionType, ProcessIdentity,
)
from .process_authorization import ProcessAuthorizationPolicy
from .windows_process_adapter import WindowsProcessAdapter


@dataclass(frozen=True)
class ProcessAuthorizationEvidence:
    """Identity-bound evidence returned by a trusted in-process evidence provider."""

    identity: ProcessIdentity
    source: str
    collected_at: datetime
    publisher_verified: bool
    signature_valid: bool
    user_owned: bool
    not_service: bool
    not_critical: bool

    def __post_init__(self):
        if not isinstance(self.identity, ProcessIdentity):
            raise TypeError("identity must be a ProcessIdentity")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("evidence source must be a non-empty string")
        if not isinstance(self.collected_at, datetime):
            raise TypeError("collected_at must be a datetime")
        if self.collected_at.tzinfo is None or self.collected_at.utcoffset() is None:
            raise ValueError("collected_at must be timezone-aware")
        for field_name in (
            "publisher_verified", "signature_valid", "user_owned",
            "not_service", "not_critical",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError("{} must be a boolean".format(field_name))

    def as_mapping(self):
        return {
            "publisher_verified": self.publisher_verified,
            "signature_valid": self.signature_valid,
            "user_owned": self.user_owned,
            "not_service": self.not_service,
            "not_critical": self.not_critical,
        }


class _WindowsGracefulCloseApi:
    """Minimal documented Win32 API wrapper; loaded only on Windows."""

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    SYNCHRONIZE = 0x00100000
    WM_CLOSE = 0x0010
    WAIT_OBJECT_0 = 0x00000000
    WAIT_TIMEOUT = 0x00000102
    WAIT_FAILED = 0xFFFFFFFF

    def __init__(self):
        if os.name != "nt":
            raise OSError("Graceful process closure is supported only on Windows")
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)

        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL
        self.kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        self.kernel32.GetProcessTimes.restype = wintypes.BOOL
        self.kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel32.WaitForSingleObject.restype = wintypes.DWORD

        self._window_enum_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user32.EnumWindows.argtypes = [self._window_enum_callback, wintypes.LPARAM]
        self.user32.EnumWindows.restype = wintypes.BOOL
        self.user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
        ]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.user32.PostMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        ]
        self.user32.PostMessageW.restype = wintypes.BOOL

    def open_action_handle(self, pid):
        rights = self.PROCESS_QUERY_LIMITED_INFORMATION | self.SYNCHRONIZE
        handle = self.kernel32.OpenProcess(rights, False, pid)
        if not handle:
            raise self._last_error("OpenProcess")
        return handle

    def get_creation_time(self, handle):
        c, w = self.ctypes, self.wintypes
        created, exited, kernel, user = w.FILETIME(), w.FILETIME(), w.FILETIME(), w.FILETIME()
        if not self.kernel32.GetProcessTimes(
            handle, c.byref(created), c.byref(exited), c.byref(kernel), c.byref(user)
        ):
            raise self._last_error("GetProcessTimes")
        ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
        return (ticks - 116444736000000000) / 10000000

    def request_window_close(self, pid):
        windows = []
        c, w = self.ctypes, self.wintypes
        callback_type = self._window_enum_callback

        def collect(hwnd, _):
            owner_pid = w.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, c.byref(owner_pid))
            if owner_pid.value == pid and self.user32.IsWindowVisible(hwnd):
                windows.append(hwnd)
            return True

        callback = callback_type(collect)
        if not self.user32.EnumWindows(callback, 0):
            raise self._last_error("EnumWindows")
        sent = 0
        for hwnd in windows:
            if self.user32.PostMessageW(hwnd, self.WM_CLOSE, 0, 0):
                sent += 1
        return sent

    def wait_for_exit(self, handle, timeout_ms):
        result = self.kernel32.WaitForSingleObject(handle, timeout_ms)
        if result == self.WAIT_OBJECT_0:
            return "exited"
        if result == self.WAIT_TIMEOUT:
            return "timeout"
        if result == self.WAIT_FAILED:
            raise self._last_error("WaitForSingleObject")
        raise OSError("Unexpected WaitForSingleObject result: {}".format(result))

    def close_handle(self, handle):
        if not self.kernel32.CloseHandle(handle):
            raise self._last_error("CloseHandle")

    def _last_error(self, operation):
        error = self.ctypes.get_last_error()
        return OSError(error, "{} failed (Windows error {})".format(operation, error))


class ProcessGracefulCloser:
    """Authorize and request normal window closure for one exact process instance.

    This service is deliberately not connected to the legacy PID-only action
    manager or Process Explorer buttons. A trusted evidence provider must be
    explicitly injected; without one, the service fails closed.
    """

    def __init__(self, backend=None, verifier=None, authorization_policy=None,
                 evidence_provider=None, timeout_ms=5000):
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms < 0:
            raise ValueError("timeout_ms must be a non-negative integer")
        self._backend = backend
        self._verifier = verifier or WindowsProcessAdapter()
        self._policy = authorization_policy or ProcessAuthorizationPolicy(panther_pid=os.getpid())
        self._evidence_provider = evidence_provider
        self._timeout_ms = timeout_ms

    def _get_backend(self):
        if self._backend is None:
            self._backend = _WindowsGracefulCloseApi()
        return self._backend

    def _result(self, request, status, message, started, verified=False, error_code=None):
        return ProcessActionResult(
            request_id=request.request_id,
            identity=request.identity,
            action=request.action,
            status=status,
            message=message,
            requested_at=request.requested_at,
            completed_at=datetime.now(timezone.utc),
            verified=verified,
            error_code=error_code,
        )

    def close(self, request: ProcessActionRequest,
              classification: Optional[Mapping[str, Any]]) -> ProcessActionResult:
        started = datetime.now(timezone.utc)
        if not isinstance(request, ProcessActionRequest):
            raise TypeError("request must be a ProcessActionRequest")
        if request.action is not ProcessActionType.REQUEST_GRACEFUL_CLOSE:
            return self._result(
                request, ProcessActionStatus.REJECTED,
                "Only graceful application closure is supported by this service.",
                started, error_code="ACTION_NOT_SUPPORTED",
            )

        try:
            verification = self._verifier.inspect(request.identity)
        except Exception as exc:
            return self._result(
                request, ProcessActionStatus.VERIFICATION_FAILED,
                "Could not verify the process identity: {}".format(exc),
                started, error_code="IDENTITY_QUERY_FAILED",
            )

        if self._evidence_provider is None:
            return self._result(
                request, ProcessActionStatus.REJECTED,
                "No trusted process-evidence provider is configured; no close request was sent.",
                started, error_code="EVIDENCE_PROVIDER_UNAVAILABLE",
            )
        try:
            evidence = self._evidence_provider.collect(request.identity)
        except Exception as exc:
            return self._result(
                request, ProcessActionStatus.REJECTED,
                "Independent process evidence could not be collected: {}".format(exc),
                started, error_code="EVIDENCE_COLLECTION_FAILED",
            )
        if not isinstance(evidence, ProcessAuthorizationEvidence):
            return self._result(
                request, ProcessActionStatus.REJECTED,
                "The evidence provider returned an unsupported result; no close request was sent.",
                started, error_code="INVALID_EVIDENCE_RESULT",
            )
        if evidence.identity != request.identity:
            return self._result(
                request, ProcessActionStatus.IDENTITY_MISMATCH,
                "Authorization evidence belongs to a different process instance.",
                started, error_code="EVIDENCE_IDENTITY_MISMATCH",
            )
        age_seconds = (datetime.now(timezone.utc) - evidence.collected_at.astimezone(timezone.utc)).total_seconds()
        if age_seconds < 0 or age_seconds > 30:
            return self._result(
                request, ProcessActionStatus.REJECTED,
                "Authorization evidence is stale or has an invalid timestamp.",
                started, error_code="STALE_EVIDENCE",
            )

        decision = self._policy.evaluate(
            request, classification, verification, evidence.as_mapping()
        )
        if not decision.allowed:
            status = (ProcessActionStatus.IDENTITY_MISMATCH
                      if decision.code == "IDENTITY_MISMATCH"
                      else ProcessActionStatus.REJECTED)
            return self._result(
                request, status, decision.reason, started, error_code=decision.code
            )

        backend = None
        handle = None
        result = None
        try:
            backend = self._get_backend()
            handle = backend.open_action_handle(request.identity.pid)
            observed_time = float(backend.get_creation_time(handle))
            if abs(observed_time - request.identity.create_time) > 0.02:
                result = self._result(
                    request, ProcessActionStatus.IDENTITY_MISMATCH,
                    "The PID changed before the close request; no window message was sent.",
                    started, error_code="IDENTITY_MISMATCH",
                )
            else:
                sent = backend.request_window_close(request.identity.pid)
                if sent <= 0:
                    result = self._result(
                        request, ProcessActionStatus.FAILED,
                        "No visible top-level application window accepted a close request.",
                        started, error_code="NO_CLOSEABLE_WINDOW",
                    )
                else:
                    outcome = backend.wait_for_exit(handle, self._timeout_ms)
                    if outcome == "exited":
                        result = self._result(
                            request, ProcessActionStatus.EXITED_VERIFIED,
                            "The application received a normal close request and process exit was verified.",
                            started, verified=True,
                        )
                    elif outcome == "timeout":
                        result = self._result(
                            request, ProcessActionStatus.STILL_RUNNING,
                            "The close request was sent, but the process is still running. Panther did not force-stop it.",
                            started, error_code="CLOSE_TIMEOUT",
                        )
                    else:
                        result = self._result(
                            request, ProcessActionStatus.VERIFICATION_FAILED,
                            "The close request was sent, but Windows could not verify the process outcome.",
                            started, error_code="WAIT_OUTCOME_UNKNOWN",
                        )
        except PermissionError as exc:
            result = self._result(
                request, ProcessActionStatus.ACCESS_DENIED,
                "Windows denied access to this process: {}".format(exc),
                started, error_code="ACCESS_DENIED",
            )
        except ProcessLookupError:
            result = self._result(
                request, ProcessActionStatus.ALREADY_EXITED,
                "The process had already exited; Panther sent no close request.",
                started, error_code="ALREADY_EXITED",
            )
        except OSError as exc:
            code = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
            status = (ProcessActionStatus.ACCESS_DENIED if code == 5
                      else ProcessActionStatus.ALREADY_EXITED if code in (87, 1168, 3)
                      else ProcessActionStatus.FAILED)
            result = self._result(
                request, status, "Windows process operation failed: {}".format(exc),
                started, error_code=str(code or "WINDOWS_API_ERROR"),
            )
        except Exception as exc:
            result = self._result(
                request, ProcessActionStatus.FAILED,
                "Graceful close failed: {}".format(exc), started,
                error_code="UNEXPECTED_ERROR",
            )
        finally:
            if handle is not None:
                try:
                    backend.close_handle(handle)
                except Exception as exc:
                    result = self._result(
                        request, ProcessActionStatus.VERIFICATION_FAILED,
                        "The action completed, but Panther could not confirm handle cleanup: {}".format(exc),
                        started, error_code="HANDLE_CLOSE_FAILED",
                    )
        return result
