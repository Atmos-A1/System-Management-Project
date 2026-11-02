# Development Phase 5 – Verified Graceful Process Closure

> This is Development Phase 5. The filename sequence (handoff_phase_14.md) is repository handoff numbering, not the development phase number. The product goal remains Panther's Process and RAM Management module.

## Objective

Add a verified, graceful-only process-close service. Panther must ask an eligible user application to close normally, verify whether the exact process instance exits, and report the outcome accurately. It must never silently escalate to force termination.

## Scope

Included:
- A Windows action handle opened with only PROCESS_QUERY_LIMITED_INFORMATION and SYNCHRONIZE rights.
- Revalidation of PID + creation time on that action handle immediately before sending a close request.
- Enumeration of visible top-level windows owned by the target PID.
- WM_CLOSE posted to those windows; no TerminateProcess, kill(), terminate(), or force escalation.
- Bounded wait for process exit using the same action handle.
- Structured ProcessActionResult statuses.
- Handle cleanup on every path.
- Fail-closed requirement for a trusted, identity-bound, fresh process-evidence provider.
- Mock-backed tests for the workflow.

Excluded:
- Force termination.
- Process suspension or priority changes.
- Adaptive resource control / PAPC.
- Enabling the Process Explorer buttons.
- Replacing or wiring the legacy PID-only ProcessActionManager.

## Files added or changed

- Added `src/panther/services/process_graceful_closer.py`
- Added `tests/test_process_graceful_closer.py`
- Updated `src/panther/services/process_authorization.py` so Panther's PID is protected by default.
- Updated `tests/test_process_authorization.py` for default self-protection and the Phase 4 force-stop boundary.
- Updated this handoff and `handoff_phase_13.md`.

## Workflow

1. Reject any action other than REQUEST_GRACEFUL_CLOSE.
2. Verify the requested ProcessIdentity with Windows.
3. Require an injected trusted evidence provider. The returned typed evidence must be bound to the same ProcessIdentity and no older than 30 seconds.
4. Run the independent authorization policy; missing confirmation, unknown classification, missing evidence or protected identity blocks the action.
5. Open a process handle with query + synchronize rights only.
6. Re-read creation time through that handle. If PID reuse is detected, send no window message.
7. Post WM_CLOSE to visible top-level windows owned by the target PID.
8. Wait for the process handle to become signaled, up to the configured timeout.
9. Report EXITED_VERIFIED only when Windows confirms process exit. A timeout is STILL_RUNNING. No automatic escalation occurs.
10. Close the process handle on all action paths. If handle cleanup cannot be confirmed, report VERIFICATION_FAILED.

## Safety boundaries

- The action service is not wired into Process Explorer and does not use the legacy PID-only action manager.
- No trusted production evidence provider currently exists in this repository. The service therefore fails closed by default with EVIDENCE_PROVIDER_UNAVAILABLE. This is intentional; do not inject ad-hoc boolean dictionaries or enable the UI action until a real provider is implemented and reviewed.
- The existing classifier's `can_terminate` value is not sufficient authorization.
- WM_CLOSE is a normal application close request, not a guarantee that user data has been saved. Applications may prompt, ignore the request or remain running.
- A timeout never triggers a kill.
- The action handle is not opened with PROCESS_TERMINATE rights.
- Force termination remains a separate later development phase and must not be added to this service.

## Tests added

Mock-backed tests cover:
- Verified exit and handle cleanup.
- Timeout reported as STILL_RUNNING with no escalation.
- No visible closeable window.
- PID reuse between initial verification and action-handle validation.
- Access denied.
- Process already gone.
- Force termination rejected.
- Missing user confirmation.
- Verification identity mismatch.
- Wait failure without false success.
- Handle cleanup failure.
- Missing, stale and identity-mismatched evidence.
- Invalid timeout.

## Validation status

Tests have been authored and committed but were not executed in this workflow. Run on the Windows development machine:

```powershell
py -m pytest tests/test_process_authorization.py tests/test_process_graceful_closer.py -q
py -m pytest -q
```

The fake-backend tests do not prove the Win32 implementation works on a real Windows session. Before enabling UI actions, perform a controlled Windows integration test against a disposable, unsaved-data-free test application and verify WM_CLOSE, timeout, exit observation and handle cleanup. Also verify the ctypes callback/API declarations on the supported Python versions.

## Acceptance gate / remaining Phase 5 work

Phase 5 service-layer implementation is committed, but it is not yet an enabled end-user feature. Do not mark the entire phase production-complete until all of the following are done:
1. Implement and test a trusted Windows evidence provider that verifies signer/signature, user ownership, service association and critical-process status, binding the evidence to the exact process identity.
2. Wire the evidence provider and closer through a background worker; never block the Qt UI thread.
3. Add a deliberate user confirmation flow showing process name, PID, executable and the possibility of unsaved work.
4. Keep the action buttons disabled for unknown, stale, inaccessible or unsupported processes.
5. Run focused tests, the full repository suite and Windows integration tests.
6. Persist structured action history before enabling the feature.

## Product goal and roadmap

This work remains part of Process and RAM Management. The intended outcome is a reliable Process Explorer, meaningful CPU/RAM monitoring, safe process controls and eventually Panther Adaptive Process Controller (PAPC), which adapts eligible resource policies to the user's active workload.

Do not expand this sequence into storage cleanup, battery management, startup management or unrelated Windows optimisation.

## Next

Continue completing Development Phase 5 by implementing the trusted Windows evidence provider, safe Qt background integration and action history. Only after the Phase 5 acceptance gate is met should development move to Development Phase 6 (separate force-stop design), and force-stop must remain disabled until separately reviewed and implemented.
