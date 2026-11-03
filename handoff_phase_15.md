# Development Phase 6 – Separate Force-Stop Workflow

> This is Development Phase 6. The handoff filename sequence is independent of the development phase number.

## Objective

Implement a separate force-stop service for a single, explicitly confirmed process instance. It must never be an automatic fallback from Graceful Close. The service must verify the process instance immediately before termination and report success only after Windows confirms exit.

## Implemented

- Added `src/panther/services/process_force_stopper.py`.
- Added `tests/test_process_force_stopper.py`.
- Added a separate Windows backend using `OpenProcess` with only the required terminate, limited-query and synchronize rights.
- Revalidates PID + creation time through the same action handle immediately before calling `TerminateProcess`.
- Waits on that same handle and reports `EXITED_VERIFIED` only after Windows signals process exit.
- Closes the action handle on every path; cleanup failure overrides the result with `VERIFICATION_FAILED`.
- Rejects Panther itself, PID 0, protected process names, non-user-app classifications, missing confirmation, missing/stale/mismatched evidence and classifier blocks.
- No automatic escalation from graceful-close timeout.
- The service is separate from the graceful-close service.

## Important limitations — not enabled in the UI

This is a service-layer implementation, not an enabled end-user feature.

- No production trusted Windows evidence provider exists yet. The service rejects requests by default with `EVIDENCE_PROVIDER_UNAVAILABLE`.
- The Version 1 classifier currently sets `can_terminate=False` for all user-application candidates. The service therefore rejects current V1 candidates.
- The Force Stop button remains hidden and no UI action invokes this service.
- No background action worker or persistent action-history integration has been added.
- The fake-backend tests do not validate real Windows behavior.
- Phase 5's outstanding acceptance work has been skipped at the user's direction; this does not mean Phase 5 is production-complete.

Do not wire the button or provide a production evidence provider by substituting caller-supplied booleans. The evidence provider must independently establish signer/signature, ownership, service association and critical-process status for the exact process identity.

## Process Explorer loading improvement

Updated `ProcessLoadThread` so discovery and classification happen batch-by-batch. The UI receives classified batches while discovery is still running instead of waiting for the complete process snapshot and then performing a second classification pass. The default batch size was reduced from 50 to 10 so the first useful results can appear sooner. Unknown/classification-error rows remain excluded by the existing Version 1 filter.

Added `tests/test_process_load_incremental.py` to assert that a classified first batch is emitted before discovery finishes.

## Validation

Tests were authored but not executed in this workflow. Run on the Windows development machine:

```powershell
py -m pytest tests/test_process_force_stopper.py tests/test_process_load_incremental.py tests/test_processes_screen.py -q
py -m pytest -q
```

Then perform controlled Windows integration tests with a disposable application and verify identity mismatch, access denial, termination request, exit observation and handle cleanup. Do not use a real application with unsaved work for destructive integration testing.

## Remaining work before enabling Force Stop

1. Implement a real trusted Windows evidence provider.
2. Reconcile the current V1 classifier's `can_terminate=False` policy with a separately reviewed action-eligibility policy.
3. Add a background action worker and deliberate confirmation UI showing process name, PID and executable, plus a clear warning that unsaved work and background tasks may be lost.
4. Persist structured action history.
5. Run focused tests, full suite and Windows integration tests.
6. Only then consider exposing Force Stop in the V1 UI.

## Next development phase

Phase 7 – Workload Detection. Keep the Version 1 application-only display scope. Version 2's advanced all-process view remains deferred.
