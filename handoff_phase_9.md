# Phase 9 – Process Reliability Foundation: Domain Models

## 1. Overview

Phase 9 begins the agreed Process Reliability Foundation for Panther System Intelligence. This phase implements only the domain-model layer and its unit tests. It does not yet change process discovery, classification, Windows integration, process actions, or the Process Explorer UI.

The implementation follows the confirmed design decisions:

- Process identity is based on PID plus process creation time.
- Name and executable path are supporting metadata, not identity keys.
- Unknown processes will be blocked from restricted actions in the authorization phase.
- Graceful closure will use a normal application window-close request in a later phase.
- Windows-specific operations will live behind a dedicated adapter layer.
- Existing public interfaces will receive temporary compatibility wrappers during migration.
- The project remains Python + PySide6 and retains the existing src-layout.

## 2. Files Added

### Domain package

- `src/panther/domain/__init__.py`
- `src/panther/domain/models/__init__.py`

### Process models

- `src/panther/domain/models/process_identity.py`
- `src/panther/domain/models/process_record.py`
- `src/panther/domain/models/process_action_request.py`
- `src/panther/domain/models/process_action_result.py`

### Tests

- `tests/test_process_domain_models.py`

## 3. Model Contracts

### ProcessIdentity

- Fields: `pid`, `create_time`, `name`, optional `exe`.
- Equality and hashing use only `(pid, create_time)`.
- Name and executable path are supporting metadata.
- PID zero is representable because Windows exposes a System Idle process record; later authorization must still prevent inappropriate actions.
- Creation time must be finite and positive.

### ProcessRecord

- Holds a ProcessIdentity and optional process metrics.
- Missing CPU and memory measurements remain `None`; they are not converted to zero.
- CPU values above 100 percent are accepted because process CPU usage can exceed 100 percent on multi-core systems.
- Snapshot timestamps are timezone-aware UTC by default.

### ProcessActionRequest

- Uses an enum for graceful-close and force-termination request types.
- Includes a unique request ID, requesting actor, explicit confirmation flag and timezone-aware request timestamp.
- Confirmation defaults to false. The model does not itself grant authorization.

### ProcessActionResult

- Uses explicit statuses for rejected, mismatched, already-exited, request-sent, verified-exit, still-running, access-denied, verification-failed and failed outcomes.
- A result with status `EXITED_VERIFIED` cannot be constructed unless `verified=True`.
- A request being sent is not treated as proof that a process exited.

## 4. Compatibility and Runtime Notes

- Type annotations use `typing.Optional` rather than Python 3.10 union syntax, preserving compatibility with the project's declared Python 3.9 baseline.
- Models are immutable dataclasses to prevent accidental mutation after a process snapshot or action request is created.
- The new package exports the four model classes and their enums.
- Existing service and UI interfaces have not yet been migrated. That is intentional; migration belongs to later phases.

## 5. Test Coverage

The new unit tests cover:

- Process identity equality, hashing and PID reuse distinction.
- PID zero representation and invalid identity values.
- Missing measurements and multi-core CPU percentages.
- Invalid CPU values and naive timestamps.
- Unique action request IDs and safe confirmation defaults.
- Rejection of untyped action values.
- Prevention of unverified successful-exit results.
- Representation of a sent-but-unverified request.

### Test result

- Command: `PYTHONPATH=src pytest -q tests/test_process_domain_models.py`
- Result: **19 passed** in the development test environment (Python 3.13.5).
- Python 3.9 runtime testing was not available in this environment; source syntax and typing choices were kept compatible with the declared 3.9 baseline.

## 6. Not Included in Phase 9

The following remain untouched and are explicitly deferred:

- Process adapter refactoring.
- Windows process handles and native API adapters.
- Process classification and authorization changes.
- Graceful window-close implementation.
- Force-termination implementation.
- Process verification service.
- Action history integration.
- Process Explorer UI changes.
- Compatibility wrappers for existing service methods.

## 7. Next Phase

**Phase 2 – Process Discovery**

1. Refactor the existing process adapter to produce ProcessRecord instances.
2. Populate ProcessIdentity using PID, creation time, name and executable path.
3. Preserve per-process exception handling.
4. Represent unavailable metrics as None.
5. Standardize CPU sampling behaviour.
6. Add tests for inaccessible and disappearing processes.
7. Keep existing callers working until the compatibility migration is ready.

No Windows process-control operations should be introduced during Phase 2.
