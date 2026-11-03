# Phase 10 – Process Reliability Foundation: Process Discovery

## 1. Overview

Phase 10 introduces a typed process-discovery API while preserving the existing dictionary-based interfaces used by Panther's current UI and services.

The preferred API is `get_process_records()`, which returns `ProcessRecord` instances. The existing `get_processes()`, `get_process_tree()` and `get_process_details(pid)` dictionary contracts remain available during migration.

No process-control operations, Windows handles, classification rules, authorization rules, or UI changes are included in this phase.

## 2. Files Changed

- `src/panther/services/process_adapter.py`
- `tests/test_process_adapter.py`

## 3. Discovery Contract

### Preferred typed API

`get_process_records() -> list[ProcessRecord]`

Each record contains:

- `ProcessIdentity(pid, create_time, name, exe)`
- parent PID, username and status when available
- CPU percentage when a valid sample exists
- RSS and VMS memory values when available
- thread count when available
- a UTC `first_seen` timestamp supplied by the model

A process without a usable PID or creation time is skipped because it cannot be represented safely by the agreed identity model. An inaccessible or disappearing process does not prevent other processes from being discovered.

### Legacy compatibility bridge

`get_processes()` continues returning dictionaries with the existing keys used by the Process Explorer. Missing numeric values are mapped to legacy defaults only in this compatibility function. New callers should use `get_process_records()` to preserve the distinction between zero and unavailable.

`get_process_tree()` and `get_process_details(pid)` remain dictionary-based for existing callers.

## 4. CPU Sampling

The typed discovery path uses non-blocking CPU-time deltas keyed by `(PID, creation_time)`. The first observation establishes a baseline and reports CPU as `None`, not 0%. Subsequent observations calculate CPU percentage from elapsed monotonic time. A changed creation time for a reused PID starts a new baseline.

This avoids blocking the discovery loop and avoids presenting the initial psutil baseline as proof that a process is idle.

## 5. Error Handling

- psutil absence raises a clear `RuntimeError`.
- Per-process access denial, disappearance, zombie state, malformed identity fields, and unexpected per-process errors are isolated to that process.
- Missing memory, CPU, username, executable, status, and thread data remain unavailable in the typed record rather than being fabricated.

## 6. Tests

`tests/test_process_adapter.py` covers:

- typed record creation and identity fields
- unavailable metrics remaining `None`
- skipping processes without creation time
- isolating an inaccessible process
- preserving the legacy dictionary interface
- first-sample CPU baseline and subsequent delta calculation
- PID reuse creating a new CPU baseline
- clear failure when psutil is unavailable

## 7. Test Results

The phase-specific adapter tests and the Phase 1 domain-model tests were run together in an isolated working copy of the implementation:

- Command: `PYTHONPATH=/mnt/data/panther_phase2/src pytest -q /mnt/data/panther_phase2/tests`
- Result: **29 passed**.
- A live process-enumeration smoke test in the Linux development container returned 17 process records.
- This is not a run of the complete repository test suite and is not Windows validation. Re-run the tests from the actual repository after applying the package, then perform Windows-specific testing.

## 8. Deferred Work

- Migrate Process Explorer and other callers to `ProcessRecord`.
- Add a typed process-details API if needed.
- Add background process discovery in the UI.
- Implement Windows process handles and adapters.
- Implement identity-aware authorization and actions.
- Add process verification and structured action history.

## 9. Next Phase

Phase 3 is Windows integration and identity verification. Before that work, inspect all remaining callers and confirm the typed discovery API is stable. No termination or process-control code should be introduced as part of this phase.
