# Development Phase 7 to 10 – PAPC (Workload Detection, Adaptive Policy Engine, Resource Control)

> Handoff document: `handoff_phase_16.md`  
> Baseline commit: `58f244b` ("phase 7 to 10") + domain model export patch  
> Target: Panther Adaptive Process Controller (PAPC) Foundation

---

## 1. Executive Summary

Commit `58f244b` integrated the core services and domain models for Panther Adaptive Process Controller (PAPC), spanning:
- **Phase 7 – Workload Detection**: System and process resource sampling, multi-sample smoothing, and workload classification (`idle`, `light`, `normal_interactive`, `heavy_cpu`, `heavy_memory`, `combined`, `unknown`).
- **Phase 8 – Adaptive Policy Engine**: Safe default rules, recommendation generation with explanations, strict enforcement of `auto_terminate = False` and `require_approval = True`.
- **Phase 9 – Resource Controller**: Explicit priority adjustment with rollback history, automatic mode disabled by default (`mode="recommendation"`), self-protection (refuses to target Panther's own PID).
- **Phase 10 – Domain Models Integration**: Unified exports for typed workload, policy, and resource control models.

---

## 2. Changes Introduced in Commit `58f244b`

### Domain Models
- `src/panther/domain/models/workload.py`:
  - `ProcessResourceSample(pid, name, cpu_percent, memory_rss, timestamp)`
  - `SystemResourceSample(cpu_percent, memory_percent, memory_available, memory_total, timestamp)`
  - `WorkloadClassification(classification, confidence, evidence, pressure, samples_count, timestamp)`
- `src/panther/domain/models/policy.py`:
  - `PolicyRecommendation(id, action_type, target_pid, target_name, reason, explanation, confidence, measurement_quality, requires_user_approval, reversible, ...)`
  - `PolicyDecision(recommendations, policy_name, safe_default, timestamp, context)`
- `src/panther/domain/models/resource_control.py`:
  - `ControlAction(id, action_type, target_pid, target_name, previous_state, new_state, reason, mode, reversible, rollback_data, result, ...)`
  - `ControlHistory(actions, automatic_enabled, mode)`

### Services
- `src/panther/services/workload_detector.py`:
  - Collects system metrics and per-process resource deltas.
  - Maintains sliding windows (`_system_samples`, `_process_samples`).
  - Classifies workload states and detects sustained consumers (>30% CPU or >500MB RAM over multiple samples).
- `src/panther/services/adaptive_policy_engine.py`:
  - Evaluates system workload states against safe policies.
  - Emits recommendations for idle monitoring reduction, heavy memory investigation, and heavy CPU investigation.
  - Never automatically terminates any process; all recommendations require explicit user approval.
- `src/panther/services/resource_controller.py`:
  - Manages process priority adjustments and restores.
  - Automatic adaptation disabled by default; requires explicit enablement.
  - Tracks actions with rollback data and maintains full audit history.
  - Prevents targeting Panther's own process.

### Tests Added
- `tests/test_workload_detector.py`
- `tests/test_adaptive_policy_engine.py`
- `tests/test_resource_controller.py`

---

## 3. Bug Identified and Resolved

### Regression in `src/panther/domain/models/__init__.py`
When `58f244b` added the new models, `ProcessActionStatus` and `ProcessActionType` were omitted from imports and `__all__`. This broke existing callers importing them from `panther.domain.models`, including:
- `src/panther/services/process_force_stopper.py`
- `src/panther/services/process_graceful_closer.py`
- `src/panther/services/process_authorization.py`
- `tests/test_process_domain_models.py`
- `tests/test_process_force_stopper.py`
- `tests/test_process_graceful_closer.py`
- `tests/test_process_authorization.py`

### Resolution
Updated `src/panther/domain/models/__init__.py` to re-export `ProcessActionStatus` and `ProcessActionType` alongside the new models, restoring full backwards compatibility.

---

## 4. Current State & Safety Boundaries

1. **Non-destructive & Conservative**:
   - `auto_terminate` is hardcoded to `False`.
   - `requires_user_approval` defaults to `True`.
   - Automatic execution in `ResourceController` is disabled by default (`mode="recommendation"`).
2. **UI Integration**:
   - The PAPC engine, workload detector, and resource controller are implemented at the service/domain layer.
   - They are not yet wired into the Qt UI threads.
3. **Evidence & Process Action Safety**:
   - Force-stop remains fail-closed and hidden in V1 UI pending a production Windows evidence provider.
