# Phase 13 – Process Action Authorization Policy (No Execution)

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
9. Force termination is represented as a separate action type. This phase only authorizes a request; it does not execute it.

The current classifier does not produce all independent trust evidence fields. Therefore the policy intentionally denies current processes until a later evidence adapter supplies them. This is safer than treating Program Files/AppData paths or process names as proof of safety.

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
- Positive authorization with all evidence present.
- Force termination remains a distinct explicitly confirmed request.

## Validation
Run:
```powershell
py -m pytest tests/test_process_authorization.py -q
py -m pytest -q
```
Tests use pure policy objects and fake verification results. They do not terminate processes. Full repository and Windows integration validation remain separate requirements.

## Safety and PRD alignment
This phase enforces least privilege, explicit confirmation, unknown-process blocking and separation of classification from authorization. It does not make the legacy PID-only process action manager safe. The Process Explorer action buttons must remain disabled until a later phase implements a verified action-handle lifecycle, graceful close, exit verification and structured audit results.

## Next
Phase 14 should implement a query/action adapter design review and safe action-result workflow. Before any real process-control operation is enabled, tests must cover stale identity, handle lifetime, access denial, timeout, process exit and verified outcomes. Force termination must remain separate and explicit; no automatic termination is permitted.
