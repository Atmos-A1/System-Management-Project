# Development Phase 4 – Process Action Authorization Policy (No Execution)

> Repository handoff filename retained for continuity. This is development Phase 4, not Phase 13. The active product goal remains the Process and RAM Management module of Panther.

## Objective
Introduce an independent, deny-by-default authorization decision for process actions. This phase separates process classification from permission. It does not execute graceful close, force termination, suspension, priority changes or other process-control operations.

## Files
- `src/panther/services/process_authorization.py`
- `tests/test_process_authorization.py`

## Authorization rules
1. Panther cannot authorize actions against its own process.
2. Explicitly protected process identities are denied.
3. Known critical Windows process names are denied.
4. A Windows verification result is mandatory and must be VERIFIED for the exact requested ProcessIdentity.
5. User confirmation is mandatory.
6. Classification must be available, identify a user application, and not block the action.
7. Classification alone is insufficient. Independent authorization evidence must affirm publisher verification, valid signature, user ownership, non-service status and non-critical status.
8. Missing, false or ambiguous evidence denies the request.
9. Force termination is explicitly rejected in Development Phase 4 with ACTION_NOT_IN_PHASE_SCOPE. It belongs to a separately reviewed future phase.

The current classifier does not produce all independent trust evidence fields. Therefore the policy intentionally denies current processes until a trusted evidence provider supplies them. This is safer than treating Program Files/AppData paths or process names as proof of safety.

## Test coverage
- Missing Windows verification.
- PID reuse / identity mismatch.
- Access denied and other non-verified statuses.
- Missing user confirmation.
- Protected Windows process names.
- Panther self-protection.
- Unknown classification.
- Classifier denial.
- Missing trust evidence.
- Each required evidence field individually absent/false.
- Positive authorization for a confirmed graceful-close request with all evidence present.
- Force termination is rejected as out of scope.

## Validation
Run:
```powershell
py -m pytest tests/test_process_authorization.py -q
py -m pytest -q
```
Tests use pure policy objects and fake verification results. They do not terminate processes. Full repository and Windows integration validation remain separate requirements.

## Safety and PRD alignment
This phase enforces least privilege, explicit confirmation, unknown-process blocking and separation of classification from authorization. It does not make the legacy PID-only process action manager safe. The Process Explorer action buttons must remain disabled until a later phase implements a verified action-handle lifecycle, graceful close, exit verification and structured audit results.

## Phase 4 implementation update
- Authorization now reports a verification result for a different ProcessIdentity as IDENTITY_MISMATCH before evaluating its verification status.
- This phase authorizes graceful-close requests only. Force termination is explicitly rejected with ACTION_NOT_IN_PHASE_SCOPE, even if the request is confirmed and all evidence fields are present.
- Added regression tests for both boundaries.
- This policy remains side-effect-free: it does not open action handles, send window messages, terminate processes, or change priorities.

## Validation status
The new and existing tests are committed, but they have not been executed in the current workflow. Run the focused test file and then the complete suite on the Windows development environment. Mocked policy tests do not establish that Windows process actions work.

## PRD alignment and scope guard
This remains exclusively the Process and RAM Management module. It advances safe process selection and user-authorized process control. It does not introduce storage cleanup, battery management, startup management, or unrelated system optimisation. RAM intelligence and adaptive allocation remain later work within this same module.

## Phase 4 completion note
Development Phase 4 policy work is committed. The policy now protects Panther's current PID by default, rejects force termination as out of scope, and has regression coverage for mismatched identity and default self-protection.

See `handoff_phase_14.md` for Development Phase 5 graceful-close implementation and its remaining integration gate.
