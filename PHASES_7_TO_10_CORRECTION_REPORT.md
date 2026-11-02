# Phases 7–10 Correction Report

**Project:** Panther System Intelligence  
**Scope:** Workload detection, adaptive recommendations, resource control, and UI integration  
**Baseline:** Uploaded `SManage` project archive (includes `handoff_phase_16.md`)  
**Status:** Corrective implementation prepared in the working copy; Windows and Qt runtime acceptance remain outstanding.

## Executive summary

The reviewed implementation had several safety and correctness gaps: workload classification could block while manufacturing samples, process discovery ran twice per sample, first CPU readings could be mistaken for real measurements, recommendations trusted PID-only consumer data, priority values were not actually allowlisted, process identity checks were separated from the mutation, and action history existed only in memory.

The corrective work replaces those paths with timestamped measurements, evidence-gated recommendations, same-handle Windows priority verification, explicit confirmation, and SQLite-backed history. A monitor-first Adaptive Control screen has also been added. Adaptive execution remains unavailable in the V1 interface.

## Phase 7 — Workload detection

- Removed the sampling loop and `sleep()` from `classify_workload()`. It now classifies only measurements already collected by a background caller.
- First system CPU sample is explicitly unavailable until a baseline exists. First process CPU sample for each `(PID, creation_time)` is also unavailable.
- Missing CPU or memory metrics remain unavailable; they are never silently converted to zero.
- Added sample-window freshness checks, minimum sample count, and minimum observation-span checks.
- Process sampling performs one process enumeration per snapshot. Stale process histories are pruned using the active identities from that same pass.
- Process histories are keyed by PID plus creation time. Sustained-consumer results carry a `ProcessIdentity`, not only a PID.
- Added available-RAM percentage as independent memory-pressure evidence.

## Phase 8 — Adaptive policy engine

- Unknown, stale, low-confidence, or insufficiently sampled workloads produce no recommendations.
- Recommendations are informational. High resource usage is not treated as evidence that an application is unnecessary.
- System pressure produces an investigation prompt, not a process action.
- A process-specific recommendation requires a typed `ProcessIdentity`, current V1 `User application` classification, a fresh sample, sufficient measurement quality, and an explicitly known non-foreground state.
- `auto_terminate` is forced off even if a caller attempts to enable it. All recommendations require approval.
- No termination, suspension, affinity, or other destructive recommendation is introduced.

## Phase 9 — Resource controller

- Replaced the psutil read/write/reopen sequence with a Windows adapter that opens one process handle with query and set-information rights, verifies creation time, reads the previous priority, applies the change, and verifies the result through that same handle.
- Automatic mode checks the foreground process independently through Windows foreground-window APIs and refuses to control it. If foreground status cannot be established, automatic control fails closed.
- Priority requests are restricted to IDLE, BELOW_NORMAL, and NORMAL. Higher priority classes are not newly requested.
- Explicit confirmation and V1 user-application eligibility are required. Automatic mode remains disabled by default.
- Non-Windows execution fails closed rather than using a weaker PID-only fallback.
- Every attempt is persisted to SQLite, including rejected and failed attempts. History survives controller recreation.
- Rollback requires a separate explicit confirmation, revalidates the exact process identity through the same-handle adapter, verifies the restored priority, records the rollback, and marks the original action as rolled back to prevent replay.

## Phase 10 — UI integration

- Added an **Adaptive Control** navigation screen.
- **Monitor (default)** displays system CPU, RAM usage, available RAM, workload, pressure, confidence, and current V1 user-application candidates.
- **Adaptive Recommendations** shows evidence-based guidance. Insufficient or stale evidence produces an explicit no-recommendation state.
- **Adaptive Control** is visibly unavailable/disabled in V1.
- Sampling, process discovery, classification, and recommendation evaluation run in a QThread worker; the UI does not sleep or perform the sampling loop on the GUI thread. Refreshes do not overlap.
- Added a resource-control action history view and a confirmation-gated rollback action for previously recorded eligible actions.
- The existing Processes screen remains the application-focused explorer. No all-process Advanced view was added.

## Preserved safety boundaries

- V1 shows user-application candidates only in the normal Processes view.
- System, protected, unknown, and unverified processes remain excluded from the normal view.
- Classification remains evidence for display/eligibility, not proof that an application is safe to close.
- Force Stop remains hidden. No automatic process termination or suspension is added.
- Phase 5 graceful-close acceptance remains deferred.
- No destructive cleanup or resource action is performed automatically.

## Verification performed

- `compileall` completed successfully for the project source.
- **123 non-Qt tests passed** in the isolated test run.
- The three Qt-dependent test modules (`test_process_load_incremental.py`, `test_processes_screen.py`, and `test_ui_dashboard.py`) could not be collected because PySide6/pytest-qt are not installed in this execution environment.
- The Win32 process-handle implementation was not executable on this non-Windows environment. It requires validation on a supported Windows 11 machine.
- No before/after UI latency benchmark was claimed because a Windows/PySide6 runtime was unavailable.

## Remaining acceptance work

1. Install the project's declared dependencies on Windows 11 and run the complete test suite, including Qt tests.
2. Exercise the Adaptive Control screen and verify sampling, navigation, hide/show, and clean application shutdown.
3. Validate the Win32 priority adapter on disposable test applications, including PID reuse, access denial, foreground protection, successful verification, and rollback.
4. Measure first-paint and first-classified-batch latency on the target Windows machine.
5. Keep Adaptive Control disabled until the above acceptance checks pass.

**Bottom line:** the service-layer defects identified in the review have been corrected and the monitor/recommendations UI has been integrated, but this is not a claim of completed Windows acceptance. Priority control remains fail-closed outside Windows and unavailable through the V1 UI.
