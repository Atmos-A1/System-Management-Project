# Phase 11 – Windows Process Identity Verification (Read-only)

## Objective

Add the first Windows-native process integration layer. This phase verifies that a PID still refers to the exact process instance represented by `ProcessIdentity(pid, create_time)`.

**This phase is query-only.** It does not terminate, suspend, change priority, alter power settings, or otherwise control processes. It does not elevate privileges.

## Files

- `src/panther/services/windows_process_adapter.py`
- `tests/test_windows_process_adapter.py`

## Behavior

- Uses documented Windows APIs through a small adapter.
- Opens a process with `PROCESS_QUERY_LIMITED_INFORMATION` only.
- Reads process creation time using `GetProcessTimes`.
- Compares the observed creation time with the requested identity; the default comparison tolerance is 20 milliseconds and is configurable for tests.
- Reads the executable image path as supporting metadata only. Failure to read the image path does not invalidate a matching PID + creation-time identity.
- Closes every successfully opened handle in a `finally` path.
- Does not open PID 0 (System Idle pseudo-process).
- Returns explicit statuses: verified, identity mismatch, already exited, access denied, unsupported, query failed.
- Never treats access denied, a query failure or a mismatch as verification success.
- The adapter is injectable so unit tests can run with a fake backend on non-Windows development systems.

## Safety boundary

The handle is closed before this query-only method returns. It is not an action handle and must not be reused for process control. Any later action phase must design a separate verified-handle lifecycle, revalidate identity immediately before acting, enforce authorization, and close handles deterministically. No action method belongs in this phase.

## Tests

`tests/test_windows_process_adapter.py` covers:

- matching identity and successful handle cleanup
- PID reuse / creation-time mismatch
- configurable creation-time tolerance
- access denied
- process already exited
- image-path failure while retaining creation-time identity
- query failure and handle cleanup
- PID 0 rejection
- invalid input type

The fake backend tests are platform-independent. A Windows integration test is still required before this phase can be called Windows-validated: inspect the current test process and a disposable child process, verify handle cleanup, and test access-denied behavior where a safe reproducible case exists. Do not target critical or unrelated processes.

## Test status

The implementation and test cases are committed as source changes. No claim of passing tests is made until they are run against the repository. Run the phase-specific test and the full repository suite in the actual development environment. Then run the controlled Windows integration test.

## PRD alignment

This phase supports the PRD's stable process identity, PID reuse handling, least privilege, adapter separation and explicit failure reporting. It does not complete process classification, dependency analysis, graceful close, force termination, action history or the full Process Explorer workflow.

## Next

Review remaining callers and integrate identity verification into process details and selection state only after unit and Windows integration validation. Process actions remain out of scope until authorization and verified action-result handling are implemented and tested.
