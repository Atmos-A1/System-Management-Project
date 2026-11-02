"""Separate, identity-bound force-stop service for explicit user requests.

This service fails closed unless a trusted authorization-evidence provider is
injected. It is intentionally not connected to the Version 1 UI.
"""
from datetime import datetime, timezone
import os
from typing import Any, Mapping, Optional

from ..domain.models import (
    ProcessActionRequest, ProcessActionResult, ProcessActionStatus,
    ProcessActionType,
)
from .process_graceful_closer import ProcessAuthorizationEvidence
from .windows_process_adapter import WindowsProcessAdapter, ProcessVerificationStatus


class _WindowsForceStopApi:
    PROCESS_TERMINATE = 0x0001
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    SYNCHRONIZE = 0x00100000
    WAIT_OBJECT_0 = 0
    WAIT_TIMEOUT = 0x102
    WAIT_FAILED = 0xFFFFFFFF

    def __init__(self):
        if os.name != "nt":
            raise OSError("Force stop is supported only on Windows")
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        self.kernel32.GetProcessTimes.restype = wintypes.BOOL
        self.kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel32.TerminateProcess.restype = wintypes.BOOL
        self.kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel32.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

    def open_action_handle(self, pid):
        rights = (self.PROCESS_TERMINATE | self.PROCESS_QUERY_LIMITED_INFORMATION
                  | self.SYNCHRONIZE)
        handle = self.kernel32.OpenProcess(rights, False, pid)
        if not handle:
            raise self._error("OpenProcess")
        return handle

    def get_creation_time(self, handle):
        c, w = self.ctypes, self.wintypes
        created, exited, kernel, user = w.FILETIME(), w.FILETIME(), w.FILETIME(), w.FILETIME()
        if not self.kernel32.GetProcessTimes(
            handle, c.byref(created), c.byref(exited), c.byref(kernel), c.byref(user)
        ):
            raise self._error("GetProcessTimes")
        ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
        return (ticks - 116444736000000000) / 10000000

    def terminate(self, handle):
        if not self.kernel32.TerminateProcess(handle, 1):
            raise self._error("TerminateProcess")

    def wait_for_exit(self, handle, timeout_ms):
        result = self.kernel32.WaitForSingleObject(handle, timeout_ms)
        if result == self.WAIT_OBJECT_0:
            return "exited"
        if result == self.WAIT_TIMEOUT:
            return "timeout"
        if result == self.WAIT_FAILED:
            raise self._error("WaitForSingleObject")
        raise OSError("Unexpected wait result: {}".format(result))

    def close_handle(self, handle):
        if not self.kernel32.CloseHandle(handle):
            raise self._error("CloseHandle")

    def _error(self, operation):
        code = self.ctypes.get_last_error()
        return OSError(code, "{} failed (Windows error {})".format(operation, code))


class ProcessForceStopper:
    """Force-stop one explicitly confirmed, independently verified app instance.

    No provider is configured in Panther today, so the default behavior is a
    rejection before opening a terminate-capable handle.
    """

    PROTECTED_NAMES = frozenset({
        "system", "system idle process", "smss.exe", "csrss.exe",
        "wininit.exe", "services.exe", "lsass.exe", "winlogon.exe",
        "svchost.exe", "dwm.exe", "ntoskrnl.exe", "registry",
    })

    def __init__(self, backend=None, verifier=None, evidence_provider=None,
                 panther_pid=None, timeout_ms=5000):
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms < 0:
            raise ValueError("timeout_ms must be a non-negative integer")
        self._backend = backend
        self._verifier = verifier or WindowsProcessAdapter()
        self._evidence_provider = evidence_provider
        self._panther_pid = os.getpid() if panther_pid is None else panther_pid
        self._timeout_ms = timeout_ms

    def _result(self, request, status, message, error_code=None, verified=False):
        return ProcessActionResult(
            request_id=request.request_id, identity=request.identity,
            action=request.action, status=status, message=message,
            requested_at=request.requested_at, completed_at=datetime.now(timezone.utc),
            verified=verified, error_code=error_code,
        )

    def force_stop(self, request: ProcessActionRequest,
                   classification: Optional[Mapping[str, Any]]) -> ProcessActionResult:
        if not isinstance(request, ProcessActionRequest):
            raise TypeError("request must be a ProcessActionRequest")
        identity = request.identity
        if request.action is not ProcessActionType.REQUEST_FORCE_TERMINATION:
            return self._result(request, ProcessActionStatus.REJECTED,
                                "This service accepts force-stop requests only.", "WRONG_ACTION")
        if identity.pid in (0, self._panther_pid) or identity.name.casefold() in self.PROTECTED_NAMES:
            return self._result(request, ProcessActionStatus.REJECTED,
                                "Protected or Panther processes cannot be force-stopped.", "PROTECTED_PROCESS")
        if not request.confirmed:
            return self._result(request, ProcessActionStatus.REJECTED,
                                "Explicit force-stop confirmation is required.", "CONFIRMATION_REQUIRED")
        if not isinstance(classification, Mapping) or classification.get("category") != "User application":
            return self._result(request, ProcessActionStatus.REJECTED,
                                "Only a classified user-application candidate can be considered.", "NOT_USER_APPLICATION")
        if classification.get("can_terminate") is not True:
            return self._result(request, ProcessActionStatus.REJECTED,
                                "The classifier has not authorized this process; no action was taken.", "CLASSIFIER_BLOCK")
        if self._evidence_provider is None:
            return self._result(request, ProcessActionStatus.REJECTED,
                                "Trusted Windows authorization evidence is unavailable; no action was taken.",
                                "EVIDENCE_PROVIDER_UNAVAILABLE")

        try:
            verification = self._verifier.inspect(identity)
        except Exception as exc:
            return self._result(request, ProcessActionStatus.VERIFICATION_FAILED,
                                "Identity verification failed: {}".format(exc), "IDENTITY_QUERY_FAILED")
        if (verification is None or verification.requested_identity != identity
                or verification.status is not ProcessVerificationStatus.VERIFIED
                or not verification.verified):
            return self._result(request, ProcessActionStatus.IDENTITY_MISMATCH,
                                "Windows did not verify this exact process instance.", "IDENTITY_NOT_VERIFIED")

        try:
            evidence = self._evidence_provider.collect(identity)
        except Exception as exc:
            return self._result(request, ProcessActionStatus.REJECTED,
                                "Authorization evidence could not be collected: {}".format(exc),
                                "EVIDENCE_COLLECTION_FAILED")
        if not isinstance(evidence, ProcessAuthorizationEvidence) or evidence.identity != identity:
            return self._result(request, ProcessActionStatus.REJECTED,
                                "Evidence is missing, unsupported or belongs to another process.",
                                "INVALID_EVIDENCE")
        age = (datetime.now(timezone.utc) - evidence.collected_at.astimezone(timezone.utc)).total_seconds()
        if age < 0 or age > 30:
            return self._result(request, ProcessActionStatus.REJECTED,
                                "Authorization evidence is stale.", "STALE_EVIDENCE")
        if not all(evidence.as_mapping().get(key) is True for key in (
            "publisher_verified", "signature_valid", "user_owned", "not_service", "not_critical"
        )):
            return self._result(request, ProcessActionStatus.REJECTED,
                                "Independent trust evidence is incomplete.", "INSUFFICIENT_TRUST_EVIDENCE")

        backend, handle, result = None, None, None
        try:
            backend = self._backend or _WindowsForceStopApi()
            handle = backend.open_action_handle(identity.pid)
            observed = float(backend.get_creation_time(handle))
            if abs(observed - identity.create_time) > 0.02:
                result = self._result(request, ProcessActionStatus.IDENTITY_MISMATCH,
                                      "PID reuse detected immediately before force stop.", "IDENTITY_MISMATCH")
            else:
                backend.terminate(handle)
                outcome = backend.wait_for_exit(handle, self._timeout_ms)
                if outcome == "exited":
                    result = self._result(request, ProcessActionStatus.EXITED_VERIFIED,
                                          "Force-stop was requested and process exit was verified.",
                                          verified=True)
                else:
                    result = self._result(request, ProcessActionStatus.VERIFICATION_FAILED,
                                          "Termination was requested but exit was not verified.",
                                          "EXIT_NOT_VERIFIED")
        except PermissionError as exc:
            result = self._result(request, ProcessActionStatus.ACCESS_DENIED,
                                  "Windows denied process access: {}".format(exc), "ACCESS_DENIED")
        except ProcessLookupError:
            result = self._result(request, ProcessActionStatus.ALREADY_EXITED,
                                  "The process had already exited.", "ALREADY_EXITED")
        except OSError as exc:
            code = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
            result = self._result(request,
                ProcessActionStatus.ACCESS_DENIED if code == 5 else ProcessActionStatus.FAILED,
                "Windows force-stop operation failed: {}".format(exc), str(code or "WINDOWS_API_ERROR"))
        except Exception as exc:
            result = self._result(request, ProcessActionStatus.FAILED,
                                  "Force-stop failed: {}".format(exc), "UNEXPECTED_ERROR")
        finally:
            if handle is not None:
                try:
                    backend.close_handle(handle)
                except Exception as exc:
                    result = self._result(request, ProcessActionStatus.VERIFICATION_FAILED,
                                          "Process outcome may be uncertain because handle cleanup failed: {}".format(exc),
                                          "HANDLE_CLOSE_FAILED")
        return result
