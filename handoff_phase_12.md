# Phase 12 – Process Explorer Responsiveness and UI Integration

## Objective
Address process-list loading delay and scrolling stutter; integrate the read-only Windows process identity verifier into selection; improve the Process Explorer layout without changing Python, PySide6, psutil, SQLite or the src layout.

## Files
- `src/panther/ui/processes.py`
- `src/panther/services/process_adapter.py`
- `tests/test_processes_screen.py`
- `tests/test_process_adapter_streaming.py`
- Existing `tests/test_windows_process_adapter.py` (WinError 87 coverage)

## Implementation
- Process enumeration and classification run in a QThread, never in the GUI event loop.
- `iter_process_records()` yields typed records incrementally from one psutil enumeration. The UI receives batches of 50 records, improving time-to-first-row.
- Process classification runs off-thread after enumeration and is applied in batches.
- Refresh requests are ignored while an existing load is active.
- Search is debounced and filtering uses QSortFilterProxyModel.
- The table uses fixed row heights, pixel scrolling, fixed metadata widths, no word wrapping and no content-driven column resizing.
- Model updates use begin/end insert/reset notifications. Table data access performs no OS calls or classification.
- Numeric fields remain numeric for sorting; unavailable CPU and memory remain unavailable.
- Selection uses ProcessIdentity (PID + creation time). A refreshed list restores selection only for the same process instance.
- Selecting a process triggers query-only Windows identity verification in a background QThread.
- Graceful close and force-stop controls remain disabled. The legacy action manager still uses PID-only operations and must not be called until authorization and verified action handling are implemented.

## UI changes
- Clear title and subtitle, resource summary cards, search and category filters.
- Details panel displays resource usage, classification evidence and Windows identity verification result.
- Loading, updated, and failure states are shown.
- Accessibility names are assigned to the process table, search and filter controls.

## Performance notes
- Incremental batches improve time-to-first-row and keep the interface responsive; they do not prove that the OS enumeration itself is faster.
- Classification is off the UI thread. Fixed row heights, cached row data and avoiding resizeColumnsToContents reduce paint/layout work during scrolling.
- Process CPU sum may exceed 100% on multicore machines. Summed working sets may double-count shared pages.
- The current refresh interval is 12 seconds. Profile on the target Windows machine before making it user-configurable.
- On refresh failure after partial enumeration, the visible rows may represent a partial current snapshot; the status explicitly reports refresh failure. Do not describe it as the last complete snapshot.

## Tests
- Table displays unavailable metrics as an em dash.
- Proxy search/category filtering.
- Numeric sorting.
- Loader runs off the GUI thread.
- Screen loads asynchronously; process actions remain disabled.
- Duplicate refresh requests do not overlap.
- PID reuse clears stale selection.
- Worker emits incremental batches.
- Adapter iterator yields typed records and preserves the complete-list API.
- Windows adapter tests cover PID reuse, access denial, process exit, handle closure and invalid PID mapping.

Run on Windows from repository root:
```powershell
$env:QT_QPA_PLATFORM = "offscreen"
py -m pytest tests/test_processes_screen.py tests/test_process_adapter_streaming.py tests/test_windows_process_adapter.py -q
py -m pytest -q
```

## Validation status
The source files were syntax-compiled in the packaging environment. The UI test suite requires PySide6 and pytest-qt and must be executed on the Windows development machine. The full repository suite and Windows integration checks remain outstanding. Do not infer successful Windows validation from mock tests.

## PRD alignment
This phase advances the PRD's Process/RAM manager, responsive UI, local monitoring and least-privilege principles. It does not complete process authorization, safe close/force-stop, action history, shared system monitoring, or process dependency analysis.

## Next phase
Phase 13 is process action authorization and safety policy. It must separate classification from permission, block unknown/unverified processes, protect Panther and system-critical processes, require explicit confirmation for restricted actions, and test every allow/deny branch. No force-termination implementation or adaptive process control is part of Phase 13.
