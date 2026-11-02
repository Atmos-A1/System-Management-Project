# Panther System Intelligence – PRD Alignment, Remediation Register and Test Plan

**Document type:** Living engineering handoff  
**PRD baseline:** `Panther_System_Intelligence_PRD.docx`, version 1.0 (extracted text is also stored as `prd_extracted.txt`)  
**Repository baseline reviewed:** `main`, after Phase 2 commits  
**Review type:** Source and documentation inspection; not a full runtime or Windows validation  
**Status:** Product is directionally aligned, but not yet fully PRD-compliant

---

## 1. Executive assessment

Panther retains the PRD's intended product identity: a local-first Windows desktop system intelligence application built with Python, PySide6, psutil and documented Windows interfaces, with SQLite persistence and test-driven development.

The current repository is a useful prototype/foundation, not a completed implementation of the PRD. Several screens and adapters exist, but their current behavior is narrower than the corresponding PRD requirements. Some process and cleanup actions also need stronger safety guarantees before they should be exposed as reliable management features.

**Overall verdict: PARTIALLY ALIGNED.** Do not describe the current product as fully meeting the PRD until the open items in this document have been implemented and verified.

### Product principles that remain mandatory

1. Unknown or incomplete evidence must never be treated as permission to act.
2. No automatic deletion, process termination, service changes or other destructive actions.
3. Prefer least privilege; do not silently elevate.
4. Keep system information local by default.
5. Distinguish measured values, OS estimates, Panther estimates and unavailable data.
6. Every functional behavior must have meaningful tests, including negative and failure cases.
7. Keep Python + PySide6, the existing `src/` layout and SQLite. Do not replace the stack or perform a broad rewrite.

---

## 2. PRD alignment matrix

Status meanings: **Partial** = a basic implementation exists but acceptance criteria are incomplete; **Gap** = required behavior is missing or not demonstrated; **Foundation** = architecture/models exist but are not integrated into the user workflow.

| PRD area | Current repository position | Required remediation |
|---|---|---|
| Application shell and navigation | Foundation exists and startup was previously verified. Navigation documented in Phase 8 does not yet expose every PRD destination. | Add Applications and Settings destinations; confirm all nine PRD destinations, empty/loading/error states, keyboard navigation and screen-reader labels. |
| Dashboard and system monitoring | Basic CPU, RAM, disk and battery adapters exist. CPU sampling uses a blocking interval; screens can collect independently. | Centralize sampling, move collection off the UI thread, add timestamps/units/unsupported states, recent CPU history and measured overhead. GPU remains capability-gated. |
| Process and RAM manager | Process list, classifier and actions exist. Phase 9 models and Phase 10 typed discovery exist but are not yet integrated into the Process Explorer. | Complete identity-safe discovery and Windows handle verification, classification evidence, dependency metadata, safe close workflow, verified results and action history. |
| Storage and file manager | Scanner, duplicate detector and cleanup manager exist. | Enforce depth limits; add progress/cancellation and scan diagnostics; protect system/app/personal/unknown data; handle junctions, symlinks, races, locked files and partial failures. |
| Duplicate detection | Size grouping and hashing foundation exists. | Revalidate files while hashing; verify candidate equality; distinguish exact duplicates from similar names; never auto-remove; test changed and unreadable files. |
| Cleanup and recovery | Cleanup functionality exists but safeguards/recovery are incomplete. | Default to Recycle Bin; permanent deletion must be separate and explicit; protect paths; validate exact targets immediately before action; record each outcome; fix empty-directory assumptions and dependency declaration. |
| Battery and power intelligence | Basic psutil charge/charging/runtime readings exist. | Add supported design/full-charge capacity and health estimate; gather supported Windows power attribution; correlate trends cautiously; label estimates and confidence; never invent per-process watts. |
| Startup/background manager | Registry Run-entry discovery exists. Disable path currently lacks a complete restore workflow; other startup sources are not covered. | Persist original registry value/name/type/source before disabling; restore exactly; add startup folders and scheduled tasks in later increments; keep services separate and never auto-disable them. |
| Application inventory/dependencies | Basic installed-app inventory exists. | Validate publisher/version/install metadata; link apps to processes/startup/services/data only with evidence; use registered uninstallers or Windows Settings, never manual folder deletion as uninstall. |
| Recommendations | Threshold-based recommendations exist. | Treat missing monitoring values as unavailable, not zero; add persistence/hysteresis, confidence, evidence, potential benefit/risk, links, dismissal state and repeat suppression. No destructive auto-execution. |
| History and activity | Generic SQLite category/detail event log exists. | Add structured action, scan, snapshot and recommendation records; timezone-aware UTC; retention controls, bounded DB size, export preview and path redaction. |
| UX/accessibility | Screens exist but behavior and styling are uneven. | Consistent design system, clear plain-language explanations, visible focus, keyboard support, accessible names, resizable layouts and clear partial-data states. |
| Privacy/security | Local persistence and sensitive-path logging filter are present. | Document collected data; keep process command lines and personal paths out of history/export by default; protect DB files; no telemetry or uploads without explicit consent. |
| Packaging/compatibility | PyInstaller setup and Windows startup evidence are documented. | Repeat clean build on supported Windows versions; verify dependencies, runtime paths, upgrade behavior and no unexpected admin requirement. |
| Testing | Some unit tests exist; test inventory is incomplete. | Build the component test matrix in Section 5. Full suite and Windows integration must pass before release claims. |

---

## 3. Functional remediation register

### 3.1 System monitoring and dashboard

**Current issues**
- `psutil.cpu_percent(interval=0.1)` blocks the calling thread.
- Dashboard, recommendations and other screens can independently query the same metrics.
- A failed read must not be converted to a healthy-looking zero.
- CPU values require a defined sampling interval and timestamp.
- GPU support is not universal and must remain optional.

**Required behavior**
- Introduce one shared monitoring service that publishes immutable timestamped snapshots.
- Run collection in a worker/thread pool; UI screens consume snapshots rather than polling the OS independently.
- Represent unsupported/unavailable readings explicitly.
- Keep CPU baseline and interval semantics consistent.
- Retain bounded recent history and configurable sampling/retention.
- Measure monitoring overhead.

**Tests**
- Unit: RAM/disk calculations, CPU sample baseline, unavailable values, timestamp and units.
- Adapter: psutil failures and unsupported devices.
- Integration: one shared sample feeds dashboard and recommendations; no duplicate collection per refresh.
- UI: loading, stale, partial, error, empty and normal states; no UI-thread blocking.
- Windows: compare supported readings with Windows tools and measure overhead.

### 3.2 Process and RAM management

**Current issues**
- PID alone is used by existing actions and selected-process state; PID reuse can target a different process.
- `psutil.Process.terminate()` is not a genuine GUI `WM_CLOSE` request.
- Some action paths can report success when only a request was sent or verification failed.
- Classifier uses process names and executable locations as strong evidence; Program Files/AppData location alone does not establish safety.
- Process Explorer converts missing CPU/memory readings to zero and hides some processes by name.
- Phase 9/10 typed identity/discovery is not yet used throughout the UI/action path.

**Required behavior**
1. Use `ProcessIdentity(pid, create_time)` as the stable process-instance identity.
2. Use a verified Windows process handle for identity queries and later actions; revalidate the instance immediately before an operation.
3. Keep classification separate from action authorization. A label such as “User application” must not automatically authorize termination.
4. Unknown/unverified processes are blocked from restricted actions.
5. Protect Panther itself and protected Windows processes/services.
6. Prefer a real normal window-close request where supported; do not silently escalate.
7. Force termination remains a separate, explicit advanced action and must not be part of adaptive automation.
8. Never report success until process exit is verified. Distinguish request sent, still running, access denied, mismatch and verification failure.
9. Preserve selection only while the full identity matches after refresh.
10. Show unavailable metrics as unavailable, not zero.

**Tests**
- Unit: identity equality/hash, PID reuse, authorization rules, protected process rules, unknown block, result-state invariants.
- Adapter mocks: access denied, process exit, invalid handle, creation-time mismatch, image-path query failure and handle cleanup.
- Action mocks: request sent is not success; timeout is still running; no silent escalation; force action requires explicit confirmation.
- UI: stale selection invalidation, unknown process controls disabled, accurate status/error feedback.
- Windows integration: query the current test process and a disposable child process only; never target critical or unrelated processes.

### 3.3 Storage scanner and file metadata

**Current issues**
- `max_depth` is accepted but must be enforced.
- Large scans need bounded work, progress and reliable cancellation.
- Permission errors and file disappearance must be recorded without aborting the whole scan.
- File metadata may change during a scan.

**Required behavior**
- Enforce maximum depth at traversal time.
- Do not follow symlinks/junctions by default; detect and report them.
- Add progress, cancellation checkpoints and partial-result reporting.
- Record skipped/error counts and reasons.
- Re-stat files before/after metadata or hashing operations; mark changed files unstable and exclude them from exact claims.
- Use bounded worker concurrency and never block the UI.
- Treat personal, application, system and unknown files as potentially important unless validated otherwise.

**Tests**
- Unit: depth boundaries, hidden-file behavior, extension/type handling and cancellation state.
- Filesystem fixtures: nested trees, empty folders, symlink/junction, permission denial, disappearing file, changing file and very large file.
- Integration: progress monotonicity, cancellation latency, partial results and no traversal outside selected root.
- UI: progress, cancel, error and partial-result states.

### 3.4 Duplicate detection

**Required behavior**
- Group by size first, then cryptographic hash.
- Revalidate size and modification identity before and after hashing.
- Verify byte equality where needed before final “exact duplicate” status.
- Present every path and potential savings as an estimate.
- Never automatically delete a duplicate.

**Tests**
- Same content/different names; same name/different content; different sizes; empty files; unreadable file; file modified during hashing; file removed during scan; hash collision/equality verification path.
- Assert no cleanup operation is triggered by scanning or duplicate discovery.

### 3.5 Cleanup and recovery

**Current issues**
- Cleanup must not infer safety from age/name/path alone.
- Directory removal must account for non-empty directories.
- Recycle Bin dependency must be declared and tested on a clean install.
- Protected paths, junctions, symbolic links and file races require explicit safeguards.

**Required behavior**
- Default action is move selected files to Recycle Bin when supported.
- Permanent deletion is a separate operation with a second explicit confirmation.
- Show exact targets, estimated space and reversibility before action.
- Exclude Windows/system paths, application dependencies, personal folders and unknown classifications from bulk cleanup.
- Revalidate file identity/path immediately before action.
- Record per-item success/failure; partial failure is not total success.
- Never claim reversible if the action was permanent or the Recycle Bin operation failed.
- Declare optional dependencies (including Send2Trash if retained) in project metadata and requirements, or use a documented Windows-native adapter.

**Tests**
- Temporary sandbox only: move to Recycle Bin adapter mocked; permanent deletion confirmation; protected path rejection; path traversal; symlink/junction; locked file; permission denied; missing file; non-empty directory; partial success; rollback/restore where supported.
- Clean-environment dependency/install test.
- Assert no test touches personal or system folders.

### 3.6 Battery and power

**Current issues**
- Current adapter is primarily a basic psutil battery wrapper; it does not satisfy the full PRD.
- Per-process power cannot be presented as exact watts without a supported source.

**Required behavior**
- Separate charge percentage, charging state, Windows-provided runtime estimate, design capacity and full-charge capacity.
- Calculate health only when both capacity values are reliable; label it as an estimate.
- Gather supported Windows power attribution where available.
- Correlate process CPU/disk/network activity with system discharge over time; show confidence and methodology.
- Do not infer causation from correlation and do not fabricate per-process watts.
- No battery or power feature should change power plans without explicit user choice.

**Tests**
- Unit: health calculation, missing/invalid capacity, charge states and estimate labels.
- Adapter mocks: no battery, unsupported API, permission/API failure, inconsistent readings.
- Integration: sampled trends, timestamp alignment and missing-data handling.
- Windows: supported-device test matrix and overhead measurement.

### 3.7 Startup and background management

**Current issues**
- Registry Run discovery is a useful start, but the current disable behavior removes an entry without a complete exact restore path.
- Startup folders, scheduled tasks and service relationships are not fully covered.

**Required behavior**
- Before disabling, persist the exact registry hive, key, value name, value data and registry type plus an operation identifier.
- Restore only if the location is still in the expected state; never overwrite an unrelated change.
- Show source, publisher, command/path and evidence.
- Add startup folders and scheduled tasks as separate adapters.
- Keep services separate from startup entries; do not automatically stop or disable services.
- Require confirmation and write structured audit history.

**Tests**
- Registry adapter mocks: enumerate, disable, exact restore, missing value, changed value, access denied, invalid data and rollback.
- Startup folder fixture tests.
- Scheduled-task adapter mocks.
- UI confirmation and undo-state tests.
- Controlled Windows integration only on disposable test entries.

### 3.8 Application inventory and dependency mapping

**Required behavior**
- Read installed application records from supported Windows sources.
- Show publisher, version, install date/location and size only when actually available.
- Link processes, startup entries, services and app data only with supporting evidence.
- Open registered uninstaller/Windows Settings; never delete application directories as an uninstall substitute.

**Tests**
- Registry/package inventory fixtures; duplicate application records; missing metadata; malformed uninstall command; access denied.
- Dependency linking positive and negative evidence tests.
- UI tests for unknown metadata and safe uninstall handoff.

### 3.9 Recommendation engine

**Current issues**
- Simple thresholds are acceptable as a first pass, but single transient readings can produce noisy recommendations.
- Missing monitor values must not default to zero.
- The PRD requires confidence, risk, evidence, why-it-matters and links.

**Required behavior**
- Accept only timestamped, valid evidence.
- Require persistence/hysteresis for transient thresholds.
- Keep measured facts separate from estimates and generic advice.
- Include issue, evidence, why it matters, benefit, risk, suggested action, confidence, safety and relevant destination.
- Rank by impact, confidence and safety; do not invent an opaque optimization score.
- Persist dismissals and suppress unchanged dismissed recommendations.
- Never auto-execute destructive actions.

**Tests**
- Threshold boundaries, unavailable data, stale samples, repeated/transient spikes, hysteresis, confidence, ordering, dismissal, changed-evidence reappearance and no auto-action.
- UI tests for evidence and links.

### 3.10 History, database and reporting

**Current issues**
- Generic `category/detail` events do not satisfy structured history and reporting requirements.
- `datetime.utcnow()` produces a naive timestamp.
- Retention, database-size controls and export privacy need implementation.

**Required behavior**
- Store timezone-aware UTC timestamps.
- Add structured records for process actions, cleanup operations, startup changes, resource snapshots, scan results and recommendation state.
- Include target identity, requested operation, outcome and error without storing unnecessary command lines or sensitive paths.
- Add retention policy, bounded storage and explicit local-history deletion.
- Export with sensitive paths omitted by default and a preview before export.
- Use schema migration/versioning rather than ad-hoc schema drift.

**Tests**
- Repository CRUD, schema migration, transaction rollback, ordering, retention, database-size limit, export redaction, export preview and timezone handling.
- Verify failed actions are recorded accurately and no sensitive command-line content is persisted by default.

### 3.11 UI, navigation and accessibility

**Required behavior**
- Match all PRD navigation destinations: Dashboard, Processes, Storage, Battery, Startup Apps, Applications, Recommendations, Activity History and Settings.
- Consistent design tokens and reusable tables/cards/dialogs.
- Clear labels, units, timestamps and distinction between measured/estimated/unavailable values.
- Keyboard navigation, visible focus, accessible names, contrast and resizable layouts.
- Background workers for scans and monitoring; UI must remain responsive.
- Explicit loading, empty, partial, error and cancelled states.

**Tests**
- pytest-qt tests for each screen's initial state, refresh, filtering/sorting, selection, error/empty/loading states, button confirmation, keyboard interaction and accessible labels.
- Navigation test verifies all PRD destinations.
- Responsiveness test ensures long work does not run on the UI thread.

---

## 4. Architecture and compatibility corrections

1. Keep Python + PySide6, `src/panther`, SQLite, psutil and documented Windows APIs.
2. Keep native Windows calls behind injectable adapters; UI never calls Windows APIs directly.
3. Keep background work in QThread/QRunnable/thread pool with cancellation and bounded concurrency.
4. Keep domain models typed and immutable where useful; unavailable data is `None`.
5. The package currently declares Python `>=3.9`. Maintain that baseline or deliberately update it with a compatibility decision; do not accidentally introduce Python 3.10-only syntax. Add a Python 3.9 CI/test job if 3.9 remains supported.
6. Add `Send2Trash` to project dependency metadata if the implementation depends on it; otherwise remove the dependency path and test the native Recycle Bin adapter.
7. Keep local data under the configured user-data directory. No cloud requirement, silent telemetry or upload of system inventory.
8. Do not rewrite the whole application. Fix one functional area at a time, preserving working interfaces through compatibility bridges.

---

## 5. Mandatory test inventory and completion gates

A feature is not complete because its screen renders. It is complete only when its behavior, failure paths, safety rules and UI states are tested.

| Component | Required tests before marking complete |
|---|---|
| Configuration/logging | Defaults, invalid settings, paths, redaction, file permissions, startup failure |
| Database/models/repositories | Validation, CRUD, migrations, rollback, timezone, retention |
| System monitor | Calculations, sample baseline, unavailable metrics, adapter errors, overhead |
| Process discovery | Typed records, inaccessible/disappearing process, PID reuse, missing metadata |
| Windows process adapter | Handle open/query/close, identity mismatch, access denied, process exit, Windows integration |
| Classifier/authorization | Every safety rule, evidence conflict, unknown block, false-safe regression |
| Process actions | Graceful request, timeout, no escalation, explicit force approval, verified exit, audit result |
| File scanner | Depth, symlink/junction, permission, cancellation, progress, changing/disappearing files |
| File classifier | System/app/personal/temp/unknown evidence, conflicts, no age-only safety decision |
| Duplicate detector | Size prefilter, hash, exact equality, changed file, unreadable file, no automatic deletion |
| Cleanup manager | Protected path, Recycle Bin, permanent deletion confirmation, partial failure, restore and sandbox isolation |
| Battery/power | Missing battery, capacity health, unsupported API, estimate labels, trend alignment |
| Startup manager | Registry exact restore, startup folder, task adapter, changed source, access denied, audit |
| App inventory | Installed records, metadata gaps, duplicates, safe uninstaller handoff |
| Recommendations | Evidence, confidence, persistence, hysteresis, dismissal, no auto-action |
| History/reporting | Structured records, retention, export redaction, privacy, failed-action logging |
| Every UI screen/widget | Rendering, state, signals, keyboard, accessibility, empty/loading/error/partial states |
| Navigation/workflows | Every PRD destination and critical end-to-end flows |
| Packaging/release | Clean install, launch, database path, dependency availability, Windows compatibility |

### Safety test rule

All destructive-operation safety rules require explicit positive and negative assertions. Use mocks, temporary directories, fixture files and disposable child processes only. Never run destructive tests against personal data, production startup entries, Windows services or critical/system processes.

### Completion evidence required

For each phase handoff, record:
- exact files changed;
- behavior added and deliberately not added;
- test command and actual result;
- environment and OS used;
- tests not run;
- known limitations;
- PRD acceptance criteria satisfied and still open.

A Linux mock test is not Windows validation. A phase-specific test run is not the full repository suite. Never state either as more than it is.

---

## 6. Adaptive controller (PAPC) – PRD alignment decision

The previously discussed Panther Adaptive Process Controller (PAPC) is an advanced direction, but the PRD v1.0 does not authorize automatic destructive management. The PRD explicitly rejects automatic process termination, file deletion and service changes without user approval.

To keep PAPC compatible with the PRD:

- First-run/default state should be **Manual / Off** until the user explicitly enables adaptive mode.
- After explicit opt-in, adaptive automation may make only narrowly scoped, reversible, non-destructive adjustments (for example, eligible process priority reduction or supported efficiency hints) under visible policies.
- Record original and Panther-applied state; restore only if the current state still equals Panther's applied value.
- Never automatically terminate, force-kill, close, suspend arbitrary apps, delete files, disable startup entries or stop services.
- Unknown processes, protected processes and ambiguous identity are excluded.
- Show current policy, reason, evidence, confidence, action history and a clear pause/disable control.

This is a deliberate reconciliation of the PAPC concept with PRD v1.0. If the product owner wants adaptive mode enabled by default, the PRD must be explicitly revised and approved first.

---

## 7. Delivery order and phase boundaries

### Phase 9 – Domain models (completed)
Typed process identity, record, action request/result models and tests. No process action integration.

### Phase 10 – Process discovery (implemented and pushed; validation limited)
Typed discovery API plus legacy dictionary bridge and CPU-time sampling. Phase-specific tests passed in an isolated working copy; full repository and Windows validation remain outstanding.

### Phase 11 – Windows process identity adapter (implemented; Windows validation outstanding)
- Query-only Windows process handle adapter verifies PID + creation time and closes handles deterministically.
- Mocked tests are present; controlled Windows integration is still required.

### Phase 12 – Process Explorer responsiveness and UI integration (pushed; Windows UI validation outstanding)
- Background process discovery and classification, incremental batches, debounced proxy filtering, fixed row sizing, identity-stable selection and query-only identity verification.
- Close and force-stop remain disabled. UI tests are present but must run with PySide6/pytest-qt on Windows.

### Phase 13 – Process authorization policy (started; no process actions executed)
- Deny-by-default policy separates classification from authorization.
- Requires verified identity, explicit confirmation and independent trust evidence; blocks Panther itself, protected identities and critical process names.
- Current classifier does not provide the independent trust evidence, so the policy intentionally denies until that evidence adapter exists.

### Subsequent workstreams (sequence may be adjusted after each review)
1. Complete classifier evidence and validate the authorization policy against real Windows metadata.
2. Design and test a verified action-handle lifecycle and action-result workflow; keep actions disabled until then.
3. Shared monitoring service and responsive dashboard/process UI.
3. Storage scanner and duplicate detection reliability.
4. Cleanup and recovery safeguards.
5. Battery and power intelligence.
6. Startup manager and exact restoration.
7. Application inventory/dependency evidence.
8. Recommendation quality and structured history/reporting.
9. UX/accessibility, packaging, compatibility and full regression.

No phase may skip its test gate. No broad refactor or technology-stack change is authorized by this roadmap.

---

## 8. Current known limitations and verification status

- Source inspection was performed against the repository's `main` branch. It is not a substitute for running the complete application.
- Phase 1 reported 19 model tests passed in its isolated development environment.
- Phase 2 reported 29 tests passed in its isolated working copy and a live process-enumeration smoke test in a Linux container.
- The Phase 2 test result is not a full repository test run and is not Windows validation.
- Windows process handles, action identity checks, graceful window close, authorization and exit verification are not yet implemented by Phases 9–10.
- Current process classifier/action/UI code remains legacy and must not be considered safe for unrestricted process management until the process workstream is complete.
- Storage, battery, startup, application, recommendation and history gaps above remain open until individually implemented and tested.

**Release rule:** Panther must not claim PRD compliance or production-ready safe optimization until all applicable acceptance criteria and test gates have evidence.
