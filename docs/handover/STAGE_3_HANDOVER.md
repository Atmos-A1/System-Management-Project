# Stage 3 Handover — Storage Subsystem

**Repository:** `https://github.com/panthera2020/System-Management-Project`
**Branch:** `feature/storage-improvements`
**Status:** Stage 3 implementation complete and published for the Linux-verifiable scope.
**Audit date:** November 2026

This document is the authoritative handover for Stage 3. It is written so that a new
developer and their coding agent can understand, verify, and safely continue the work
without access to the original conversation.

---

## A. Project overview

### What Panther System Intelligence is

Panther System Intelligence is a Python/PySide6 desktop application for system
monitoring and management. It provides dashboards for CPU, memory, disk and other
system metrics, a storage-management area, and supporting services for scanning,
history, cleanup and duplicate detection.

### Purpose of the Storage subsystem

The Storage subsystem gives the user visibility and control over disk usage:

- Browse directories safely without modifying them.
- Understand where space is used, by folder and by file type.
- Inspect file metadata and leading-byte signatures without executing files.
- Work efficiently with large result sets through table models, filtering and sorting.
- Review and page through a read-only history of scan activity.
- Move user-selected files to the Recycle Bin through a guarded cleanup workflow.

### Scope and objectives of Stage 3

Stage 3 delivered five batches:

| Batch | Objective |
| --- | --- |
| 3A | Read-only Storage Explorer with navigation, bounded listing and safe metadata. |
| 3B | Folder-size and file-type insights, with cancellation and partial results. |
| 3C | Safe metadata and file-signature inspection, including race revalidation. |
| 3D | Model-backed filtering/sorting and large-result handling without losing record identity. |
| 3E | Scan-history filtering, pagination and stable ordering, using summary-only records. |

A post-audit follow-up also fixed test-database isolation so the suite no longer writes
scan history to the user's real application database. See section B.6.

Stage 3 deliberately did **not** change the production database architecture, scan-history
schema or cleanup semantics. Existing cleanup and duplicate-review workflows remain the
only paths that can move files, and they remain Recycle Bin-only.

---

## B. Stage 3 implementation summary

### 3A — Read-only Storage Explorer

**Implemented**

- A one-directory-at-a-time browser. It does not recurse during listing.
- Navigation history: back, forward, up, refresh, and direct path entry.
- Directory listing with a default limit of 2,000 entries; the result reports when it
  was truncated.
- Entry type, size, modified time, hidden state, link/reparse state and error handling.
- A metadata/signature detail pane for the selected regular file.
- Explicit rejection of symlinks and reparse points before inspection.
- Background listing and inspection workers with generation checks so stale results are
  discarded after navigation or a newer request.
- Shutdown/cancellation handling for worker threads.

**Important files**

- `src/panther/services/directory_browser.py` — `DirectoryBrowser`, listing and entry
  formatting, `DEFAULT_LIST_LIMIT = 2000`.
- `src/panther/services/file_metadata.py` — metadata inspection.
- `src/panther/services/file_signature.py` — leading-byte signature inspection.
- `src/panther/services/file_inspector.py` — combines metadata and signature results.
- `src/panther/ui/explorer.py` — `ExplorerWidget`, `_DirectoryWorker`,
  `_DirectoryThread`, `_InspectionWorker`, `_InspectionThread`.
- `src/panther/ui/storage.py` — hosts the Explorer tab.

**Main design decisions**

- Listing uses `os.scandir`/`os.lstat`; links are identified but never traversed.
- Sorting is performed on records held in the UI model, not by touching the filesystem
  again.
- Inspection is dispatched only for regular, non-link entries.
- Generation counters protect against results arriving after the user has navigated away.

**Safety constraints**

- Explorer is read-only. It has no rename, delete, write or cleanup controls.
- Symlinks/reparse points are displayed but not followed or inspected.
- Inspecting a file opens it only through the signature service, with bounded reads
  (see 3C).

**Tests added**

- `tests/test_directory_browser.py` — 10 tests.
- `tests/test_ui_storage_explorer.py` — 12 tests.
- `tests/test_ui_storage_inspector.py` — 9 tests.

**Known limitations**

- Real Windows junctions and reparse points have not been exercised; Linux tests use
  simulated `st_file_attributes`.
- Network/UNC latency and very large directories have not been benchmarked.

---

### 3B — Folder Size and File-Type Insights

**Implemented**

- Iterative (non-recursive) traversal of one or more roots.
- Folder-size aggregation, including nested files and files directly in the root.
- File-type aggregation with case-insensitive extensions, an explicit extensionless
  bucket and an "other" bucket.
- Percentage calculation and formatting.
- Hardlink deduplication using device/inode identity.
- Symlink/reparse entries are excluded from size and type totals.
- Bounded collection of file types and error records.
- Progress reporting, cancellation, and distinct completed/partial/cancelled/failed
  states.
- Navigation from a folder row to the existing read-only Explorer.

**Important files**

- `src/panther/services/storage_analysis.py` — `StorageAnalysis`, `_hardlink_key`,
  `_is_link_or_reparse`, `_directory_key`.
- `src/panther/ui/insights.py` — `InsightsWidget`, `_AnalysisWorker`,
  `_AnalysisThread`, `folder_opened` signal.
- `src/panther/ui/storage.py` — connects `folder_opened` to `_open_folder_in_explorer`.

**Main design decisions**

- Traversal uses an explicit stack, avoiding Python recursion limits.
- Hard-linked files are counted once per device/inode within an analysis run.
- Aggregation is capped so pathological trees cannot grow result payloads without bound.
- Analysis results are informational and never alter cleanup authorization.

**Safety constraints**

- Insights is read-only: no writes, deletes or `_scan_roots` changes.
- Symlinks/reparse points are not followed.
- Opening a folder only calls `ExplorerWidget.navigate_to()`, which is itself read-only.

**Tests added**

- `tests/test_storage_analysis.py` — 14 tests.
- `tests/test_ui_storage_insights.py` — 13 tests.

**Known limitations**

- Cross-root hardlink accounting needs deeper validation; deduplication is by
  device/inode during one run.
- Nested folder-size semantics (how sizes roll up across multiple roots) should be
  validated against expected product behaviour before release.
- Reparse-point behaviour is Linux-simulated only.

---

### 3C — Safe Metadata and File-Signature Inspection

**Implemented**

- Metadata retrieval using `os.lstat`.
- Entry type, extension, classification, size, timestamps, hidden/read-only attributes
  and link/reparse state.
- Creation-time reporting only where reliable: `st_birthtime` where present, or the
  Windows `st_ctime` convention. Otherwise the value is reported as unavailable.
- Signature detection for a bounded set of common formats based on the first bytes.
- A maximum read of 64 bytes (`MAX_SIGNATURE_BYTES = 64`).
- No-follow open where the platform supports `O_NOFOLLOW`.
- Post-open `fstat` revalidation of file type, device/inode and size.
- Explicit `changed` result when the entry disappears or changes during inspection.
- Explicit `unreadable`/error result for permission and I/O failures.
- Descriptor closure in `finally`.
- Cancellation and stale-result protection in the UI.

**Important files**

- `src/panther/services/file_metadata.py` — `FileMetadataInspector`.
- `src/panther/services/file_signature.py` — `FileSignatureInspector`,
  `MAX_SIGNATURE_BYTES`, `_changed`.
- `src/panther/services/file_inspector.py` — `FileInspector` orchestration.
- `src/panther/ui/explorer.py` — inspection workers and detail rendering.

**Main design decisions**

- Only a short prefix is read; the file is never executed, parsed as an archive, or
  written to.
- Identity is checked before and after opening so a replaced file is rejected rather
  than misreported.
- Unsupported or unknown signatures return an explicit "unknown" result instead of
  guessing.

**Safety constraints**

- Read-only. No content modification, execution, preview extraction or archive
  expansion.
- Links/reparse points are rejected before opening.
- Bounded reads and descriptor cleanup are enforced.

**Tests added**

- `tests/test_file_metadata.py` — 12 tests.
- `tests/test_file_signature.py` — 14 tests.
- UI coverage in `tests/test_ui_storage_inspector.py`.

**Known limitations**

- Windows lacks `O_NOFOLLOW`; protection there relies on pre-open link rejection plus
  post-open `fstat` revalidation. Real Windows TOCTOU behaviour is not yet validated.
- ACLs, locked files and actual Windows metadata semantics remain unverified.

---

### 3D — Model-Backed Filtering and Large-Result Handling

**Implemented**

- `RecordTableModel`, `RecordFilterProxyModel`, `RecordTableView` and supporting
  delegates.
- Model-backed views for Largest Files, duplicate groups, Explorer entries, folder
  sizes and file types.
- Text filtering and column sorting through proxy models.
- Proxy-to-source index mapping so the selected row always resolves to the correct
  underlying record.
- Large synthetic coverage: 2,000 Largest Files records and 3,000 generic model
  records in tests.
- Duplicate group review with explicit keep-copy logic and last-copy protection.
- Cleanup target identity derived from source records, not proxy row numbers.

**Important files**

- `src/panther/ui/table_models.py` — model, proxy, table view, delegates.
- `src/panther/ui/duplicate_review.py` — `DuplicateSelection`,
  `DuplicateReviewWidget`.
- `src/panther/ui/storage.py` — Largest Files and Duplicates tabs, filter wiring,
  cleanup triggers.
- `src/panther/ui/explorer.py`, `src/panther/ui/insights.py` — use the shared models.

**Main design decisions**

- Filtering/sorting operate on in-memory records; filesystem operations are not repeated
  for display.
- Selection is always resolved through `record_for_index`/`mapToSource`.
- Duplicate selection stores removal paths; the group records themselves are never
  mutated. Removing every copy is rejected.
- `keep_only`, `keep_newest`, `keep_oldest` and `keep_shortest_path` deterministically
  retain at least one copy.

**Safety constraints**

- Filtering or sorting cannot change which filesystem path is passed to cleanup.
- Cleanup remains constrained to the recorded scan root and existing safety policy.
- Duplicate last-copy protection is enforced in `DuplicateSelection.set_remove`.

**Tests added**

- `tests/test_record_models.py` — 6 tests.
- `tests/test_ui_storage_filtering.py` — 11 tests.
- `tests/test_duplicate_review.py`, `tests/test_duplicate_detector.py`.
- Existing storage/navigation tests cover cleanup identity.

**Known limitations**

- This is in-memory model/view filtering, not virtualized filesystem browsing. Do not
  claim unlimited scalability.
- Modified-time sorting in the shared model currently uses the display string rather
  than a numeric timestamp. This is a known limitation; validate ordering expectations
  before relying on it for chronological decisions.

---

### 3E — Scan History Filtering and Pagination

**Implemented**

- Summary-only scan history records under category `storage_scan`.
- Filters for scan kind, status, date range and text search, individually and combined.
- Clearing individual filters and all filters.
- Paginated retrieval with a default page size of 25 and a maximum of 500.
- Stable ordering: `ORDER BY ts DESC, id DESC`.
- `max_id` anchoring so events appended after the first page load do not shift or
  duplicate rows during normal navigation.
- Page clamping, total count and range labels.
- Empty, loading and error states.
- Read-only history queries only.

**Important files**

- `src/panther/services/storage_history.py` — `record_scan`,
  `get_scan_history`, `get_scan_history_page`, `EVENT_CATEGORY = "storage_scan"`.
- `src/panther/services/history.py` — generic history table and `record_event`.
- `src/panther/db.py` — `Database` and the module-level `db` singleton.
- `src/panther/ui/storage.py` — Scan History tab, filters, pagination, `_record_scan_history`.

**Main design decisions**

- Filtering and pagination happen in SQLite, using `json_valid`/`json_extract` for kind
  and status and `LIKE` with escaping for text search.
- History remains summary-only: status, kind, root, counts, duration, skipped count and
  an optional truncated error. No individual file paths or sensitive metadata are
  persisted.
- Existing scans call `_record_scan_history` on completion, cancellation and failure.
- History cannot authorize cleanup and does not modify `_scan_roots`.

**Safety constraints**

- Read-only UI. No delete, edit or clear-history control was added.
- History records are informational only.
- The history table is not used to reconstruct or approve cleanup targets.

**Tests added**

- `tests/test_storage_history.py` — 9 tests.
- `tests/test_storage_history_filters.py` — 12 tests.
- `tests/test_ui_storage_history_filters.py` — 16 tests.

**Known limitations**

- Pagination uses `OFFSET`; this is fine at current sizes but degrades on very large
  histories.
- No dedicated history index was added.
- Date filters use date strings against the stored naive-UTC timestamp domain; they are
  not local-time conversions.
- Text search uses `detail LIKE`, so it can match JSON field names as well as values.
- Malformed history records may be skipped for display while the page range label still
  reflects the database total.
- SQLite JSON1 support is required for kind/status filtering.

---

### B.6 Test-database isolation follow-up

**Original problem**

`src/panther/db.py` creates a module-level singleton at import time:

```python
db = Database()
```

`src/panther/services/history.py` imports that object by value:

```python
from ..db import db
```

`storage_history` accesses it through `history.db`. Existing tests that called
`StorageScreen._on_scan_finished()`, `_on_scan_cancelled()` or `_on_scan_failed()`
therefore wrote real history rows to the configured application database unless they
explicitly mocked `record_scan`.

**Why changing the configured database path alone was insufficient**

The old `temp_db` fixture changed `config.db_path` after the singleton had already been
constructed. The singleton and the `history.db` reference still pointed at the original
database. The fixture was also session-scoped, non-autouse and unused.

**The autouse `isolated_history_db` fixture**

`tests/conftest.py` now defines a function-scoped autouse fixture that:

1. Captures the normal database path for protection assertions.
2. Creates a fresh `Database` in its own `tmp_path_factory` directory.
3. Patches `panther.db.db` and `panther.services.history.db` to the temporary database.
4. Sets `PANTHER_DB_PATH` so subprocess-based tests inherit the temporary path.
5. Ensures the history schema exists.
6. Yields `{"db": test_db, "normal_path": normal_path}`.
7. Relies on `monkeypatch` to restore all references and environment variables after
   each test.

The database is deliberately placed outside each test's `tmp_path`, so directory-scanning
tests do not see an extra `history.db` file in their fixture tree.

**Protection and regression tests**

`tests/test_test_isolation.py` contains 7 tests:

- Scan completion writes only to the isolated database.
- Cancellation and failure use the isolated database.
- All relevant module references are redirected.
- The temporary database starts empty.
- A second test also starts empty (no shared history).
- Mocked history recording still works and writes nothing.
- A subprocess records only to the isolated database.

The protection tests read the normal database with a read-only SQLite URI and compare its
history count before and after the operation. They never write to the normal database.

**Result**

The full suite no longer changes the normal application database's size, mtime or history
row count.

---

## C. Architecture and integration

### Component map

```text
StorageScreen (src/panther/ui/storage.py)
├── Overview
├── Largest Files
│   ├── ScanController (src/panther/ui/scan_controller.py)
│   ├── FileScanner (src/panther/services/file_scanner.py)
│   ├── RecordTableModel/proxy (src/panther/ui/table_models.py)
│   └── CleanupReviewDialog + CleanupManager
├── Duplicates
│   ├── DuplicateDetector (src/panther/services/duplicate_detector.py)
│   ├── DuplicateReviewWidget/DuplicateSelection
│   └── CleanupReviewDialog + CleanupManager
├── Explorer
│   ├── DirectoryBrowser
│   ├── FileInspector -> FileMetadataInspector + FileSignatureInspector
│   └── RecordTableModel/proxy
├── Insights
│   ├── StorageAnalysis
│   └── folder_opened -> ExplorerWidget.navigate_to
└── Scan History
    ├── storage_history.get_scan_history_page
    └── history.record_event / history table
```

### Read-only versus cleanup-capable

| Component | Read-only? | Can initiate cleanup? |
| --- | --- | --- |
| Explorer | Yes | No |
| Insights | Yes | No |
| Metadata/signature inspection | Yes | No |
| Scan History | Yes | No |
| Largest Files view/filtering | Display is read-only | Cleanup button delegates to existing cleanup workflow |
| Duplicates view/filtering | Display/selection is read-only | Cleanup button delegates to existing cleanup workflow |
| `CleanupManager` | No — moves files | Yes, Recycle Bin only |
| `DuplicateSelection` | Selection state only | No direct cleanup |

### Integration points

- **Insights → Explorer:** `InsightsWidget.folder_opened` is connected to
  `StorageScreen._open_folder_in_explorer`, which calls
  `ExplorerWidget.navigate_to(path)`.
- **Explorer selection → inspection:** the selected proxy index is mapped to the source
  record before metadata/signature work starts.
- **Filtering/sorting → cleanup identity:** cleanup paths come from selected source
  records, not visible row numbers.
- **Scan completion → history:** `_on_scan_finished`, `_on_scan_cancelled` and
  `_on_scan_failed` call `_record_scan_history`, which records a summary through
  `storage_history.record_scan`.
- **Scan completion → cleanup authorization:** only a completed, non-partial scan sets
  `_scan_roots[kind]`; history display does not.
- **Worker shutdown:** Explorer, Insights and ScanController cancel and join workers and
  discard stale generations.

### Cleanup path (existing workflow, unchanged in intent)

1. User runs a scan in Largest Files or Duplicates.
2. A completed, non-partial scan records its root in `_scan_roots`.
3. User selects files or duplicate copies.
4. Cleanup review shows the intended targets.
5. `CleanupManager.move_to_recycle_bin(paths, allowed_roots)` preflights paths, then
   revalidates each path immediately before calling `send2trash`.
6. Permanent deletion is not supported. Missing `send2trash` fails closed.

---

## D. Verification results

The following results were produced by the previous Stage 3 verification and isolation
follow-up runs. They are recorded here as historical evidence. **They were not re-run
while writing this handover unless explicitly stated otherwise.** Re-run them locally
before relying on them.

### Environment used

- Python 3.14.3
- PySide6 6.12.0
- SQLite 3.51.2
- Linux
- Test command prefix:
  `QT_QPA_PLATFORM=offscreen PYTHONPATH=src <python> -m pytest -q`

### Results

| Check | Result |
| --- | --- |
| Test-database isolation tests (`tests/test_test_isolation.py`) | 7 passed |
| Focused history/scanning/storage suite | 75 passed |
| Full suite | 266 passed, 1 known failure |
| Reordered focused run | 75 passed |
| `py_compile` on changed Python files | passed |
| `git diff --check` | clean (exit 0) |

Focused suite command used:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m pytest -q \
  tests/test_test_isolation.py \
  tests/test_ui_storage.py \
  tests/test_storage_navigation.py \
  tests/test_scan_lifecycle.py \
  tests/test_storage_history.py \
  tests/test_storage_history_filters.py \
  tests/test_ui_storage_history_filters.py
```

Full suite command used:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m pytest -q
```

### Known unrelated failure

`tests/test_ui_dashboard.py::test_dashboard_loads` fails with:

```text
AttributeError: 'DashboardScreen' object has no attribute 'cpu_label'
```

The existing dashboard uses `cpu_card`, not `cpu_label`:

```python
self.cpu_card = self.create_card("CPU", "0%")
```

This failure predates Stage 3, is unrelated to the Storage subsystem, and was
intentionally left untouched. Do not "fix" it as part of Stage 3 review unless it is
scoped as a separate task.

### Normal database protection evidence

During the isolation follow-up, the normal application database at
`%LOCALAPPDATA%\PantherSystemIntelligence\data\panther.db` was observed before and after
the full suite and reordered runs:

- size unchanged
- mtime unchanged
- history row count unchanged

The tests themselves only read it through a read-only SQLite URI.

---

## E. Windows validation outstanding

Stage 3 is **Linux-complete**, not yet cross-platform release-validated. Feature
behaviour is implemented; Windows confirmation is a release-validation gate, not evidence
that the Linux implementation is incomplete.

The following must be executed on a real Windows machine and the results recorded:

- [ ] Junctions, symbolic links and reparse points: detection, non-traversal, inspection
      rejection and cleanup rejection.
- [ ] ACLs and protected directories: access-denied behaviour, protected system folders,
      and cleanup refusal.
- [ ] Locked files and access-denied behaviour during listing, metadata inspection,
      signature inspection and cleanup.
- [ ] Long paths over 260 characters, UNC paths (`\\server\share`) and extended-length
      paths (`\\?\`).
- [ ] Case-insensitive path handling and 8.3 short-name aliases.
- [ ] Windows-specific file metadata: creation time, attributes, hidden/read-only state.
- [ ] Signature inspection and TOCTOU safety without `O_NOFOLLOW`.
- [ ] Recycle Bin behaviour and per-file cleanup outcomes (moved, rejected, failed).
- [ ] Packaged `Send2Trash` availability and runtime import in the built application.
- [ ] SQLite JSON1 support in the packaged Windows runtime.
- [ ] Packaged application startup and full dependency loading.

Use the Windows machine to run the full suite and a manual smoke test of Explorer,
Insights, inspection, cleanup and history. Record both automated and manual evidence.

---

## F. Known limitations and risks

### Confirmed limitations

1. **Test environment lacked `send2trash`.** The Linux audit environment reported
   `ModuleNotFoundError`. `CleanupManager` fails closed when the dependency is absent,
   so real Recycle Bin movement was not exercised there.
2. **History pagination uses `OFFSET`.** This is simple and correct at current sizes but
   becomes slower on very large histories. No dedicated index was added.
3. **History text search is broad.** It uses `detail LIKE` and can match JSON field names
   as well as values.
4. **Malformed history rows can affect range labels.** Rows that fail JSON parsing are
   skipped for display, but the displayed page range still derives from the database
   total. A page can therefore show fewer rows than its stated range.
5. **Modified-time sorting uses display strings.** The shared table model's sort key for
   modified time is not a numeric timestamp. Validate ordering before relying on it for
   chronological decisions.
6. **No virtualization or unlimited-scale guarantee.** Model/view removes per-cell widget
   overhead but still holds results in memory.
7. **SQLite JSON1 is required** for history kind/status filtering.

### Items requiring further validation (not confirmed defects)

1. **Windows filesystem behaviour** generally: junctions, reparse points, ACLs, locked
   files, long/UNC paths, case-insensitivity, 8.3 aliases.
2. **Windows signature-inspection race protection.** The implementation relies on
   pre-open `lstat` rejection and post-open `fstat` revalidation because Windows lacks
   `O_NOFOLLOW`.
3. **Cross-root hardlink accounting.** Deduplication is by device/inode within an
   analysis run; multi-root and cross-volume semantics need product-level confirmation.
4. **Nested folder-size semantics.** How sizes roll up across multiple selected roots
   should be checked against expected behaviour.
5. **Packaged Windows runtime.** `Send2Trash`, SQLite JSON1 and packaged startup must be
   confirmed in the built executable.
6. **Recycle Bin outcomes.** Mocked tests cannot prove real Windows Recycle Bin
   behaviour or per-file results.

### Explicitly out of scope / not changed

- The dashboard `cpu_label`/`cpu_card` failure.
- Production database architecture.
- Scan-history schema and event semantics.
- Cleanup authorization rules and permanent-deletion prohibition.
- Batches 3A–3E behaviour.

---

## G. Instructions for the next developer and coding agent

### First actions

1. Read this handover document completely.
2. Inspect the current branch, commit history and working tree:
   ```bash
   git branch --show-current
   git log --oneline -10
   git status --short
   ```
3. Review the Stage 3 implementation and tests listed in section B.
4. Verify the documented results by running the focused suite and the full suite.
5. Resolve only genuine review findings. Do not reopen completed batches without
   evidence of a defect.
6. Prioritise the Windows validation checklist in section E and record the evidence.
7. Continue with the next formally planned project stage only after reviewing the
   repository's existing planning documents (`README.md`, `prd_extracted.txt`,
   `handoff_phase_6.md`, `handoff_phase_7.md`, `handoff_phase_8.md`).
8. Do not invent a next stage or add features without consulting those planning
   documents.

### Verification commands

```bash
# From the repository root, with the project environment active:
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m pytest -q
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m pytest -q \
  tests/test_test_isolation.py \
  tests/test_ui_storage.py \
  tests/test_storage_navigation.py \
  tests/test_scan_lifecycle.py \
  tests/test_storage_history.py \
  tests/test_storage_history_filters.py \
  tests/test_ui_storage_history_filters.py
python -m py_compile tests/conftest.py tests/test_test_isolation.py
git diff --check
```

Expected: all focused tests pass; full suite passes except the known dashboard failure
described in section D.

### Suggested initial prompt for a coding agent

> Read `docs/handover/STAGE_3_HANDOVER.md` and inspect the current repository state.
> Understand the completed Stage 3 Storage implementation before making changes. Verify
> the documented tests and identify any genuine unresolved defects. Prioritise the
> outstanding Windows validation requirements. Do not reopen completed batches without
> evidence of a defect. Preserve existing work, follow TDD, and provide a consolidated
> review report before proposing implementation changes.

### Working agreements

- Preserve all existing uncommitted work unless explicitly asked to change it.
- Follow TDD for any behaviour change: failing test first, then the smallest fix.
- Keep Explorer, Insights, inspection and History read-only.
- Never bypass `CleanupManager`, cleanup policy, scan-root authorization or duplicate
  last-copy protection.
- Do not add permanent deletion.
- Do not write tests that touch the real application database; use the autouse
  `isolated_history_db` fixture or an explicit temporary database.
- Do not commit, push, reset, clean or rewrite history without explicit instruction.
- Do not modify the known dashboard failure as part of Storage work.

---

## Appendix — Stage 3 file inventory

### Production files (tracked, modified)

- `build_installer.py`
- `pyproject.toml`
- `requirements.txt`
- `src/panther/db.py`
- `src/panther/services/cleanup_manager.py`
- `src/panther/services/duplicate_detector.py`
- `src/panther/services/file_scanner.py`
- `src/panther/ui/storage.py`

### Production files (new)

- `src/panther/services/cleanup_policy.py`
- `src/panther/services/directory_browser.py`
- `src/panther/services/file_inspector.py`
- `src/panther/services/file_metadata.py`
- `src/panther/services/file_signature.py`
- `src/panther/services/storage_analysis.py`
- `src/panther/services/storage_history.py`
- `src/panther/ui/cleanup_review.py`
- `src/panther/ui/duplicate_review.py`
- `src/panther/ui/explorer.py`
- `src/panther/ui/insights.py`
- `src/panther/ui/scan_controller.py`
- `src/panther/ui/table_models.py`

### Test files (new)

- `tests/test_cleanup_manager.py`
- `tests/test_cleanup_policy.py`
- `tests/test_cleanup_review.py`
- `tests/test_directory_browser.py`
- `tests/test_duplicate_detector.py`
- `tests/test_duplicate_review.py`
- `tests/test_file_metadata.py`
- `tests/test_file_scanner.py`
- `tests/test_file_signature.py`
- `tests/test_record_models.py`
- `tests/test_scan_controller.py`
- `tests/test_scan_lifecycle.py`
- `tests/test_storage_analysis.py`
- `tests/test_storage_history.py`
- `tests/test_storage_history_filters.py`
- `tests/test_storage_navigation.py`
- `tests/test_test_isolation.py`
- `tests/test_ui_storage.py`
- `tests/test_ui_storage_explorer.py`
- `tests/test_ui_storage_filtering.py`
- `tests/test_ui_storage_history_filters.py`
- `tests/test_ui_storage_insights.py`
- `tests/test_ui_storage_inspector.py`

### Test infrastructure (tracked, modified)

- `tests/conftest.py`

### Documentation (new)

- `docs/handover/STAGE_3_HANDOVER.md`
