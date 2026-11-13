# Windows Delivery — Summary and Status

**Branch:** `feature/storage-improvements`
**Purpose:** Package Panther as an installable Windows 10/11 x64 Tauri 2 desktop app with a frozen Python JSON-RPC sidecar, NSIS installer, and CI verification pipeline.

> **Status in one line:** implementation and local Linux verification are complete; **the Windows pipeline has not yet passed**. Nothing is committed or pushed. A Windows run is required to close the delivery claim.

---

## 1. Implementation Complete

### Sidecar Freezing
| Component | Status |
|-----------|--------|
| `run_sidecar.py` | PyInstaller entrypoint: UTF-8 stdio, watchdog activation only when frozen, forwards `PANTHER_PARENT_PID` |
| `build_sidecar.py` | Deterministic PyInstaller build: `--onefile --console`, hidden imports, Qt exclusions, 80 MB guard, cross-compile guard |
| `src/panther/sidecar/parent_watchdog.py` | Orphan prevention with injected dependencies; watches the *owner* PID, not `os.getppid()` |
| `src/panther/sidecar/transport/stdio.py` | `configure_stdio()`: UTF-8 `backslashreplace`, `\n` newlines, stdout line-buffered, stdin universal newlines |

**Packaging strategy:** PyInstaller onefile `--console`. Onedir rejected (Tauri `externalBin` copies files, not dirs). Nuitka rejected (no MSVC toolchain).

### Tauri Lifecycle
| Component | Change |
|-----------|--------|
| `src-tauri/tauri.conf.json` | `externalBin: ["binaries/panther-sidecar"]`, `targets: ["nsis"]`, `nsis.installMode: "currentUser"` |
| `src-tauri/src/main.rs` | `SidecarRef = Arc<Mutex<Option<SidecarHandle>>>`. Bundled spawn uses `set_process_group(true)` and sets `PANTHER_PARENT_PID` to the app's own PID. Spawn failure manages state as `None` and returns `Ok(())` so commands surface an honest error. |
| `src-tauri/src/commands/metrics.rs` | Uses `State<'_, SidecarRef>`; absent sidecar returns: `"system service is not running; Panther may not have installed correctly"` |

**Why `set_process_group(true)`:** a PyInstaller onefile executable is a level-1 bootloader plus a level-2 grandchild hosting the interpreter. Without the process group, tauri-plugin-shell's kill path falls back to `Child::kill()`, which terminates only the direct child and leaves the grandchild orphaned. With it, the plugin assigns the child to a Windows Job Object (or POSIX process group) and `send_kill()` calls `TerminateJobObject`, killing the whole tree. Verified against vendored `tauri-plugin-shell` 2.6.0 (`src/process/mod.rs`, `src/process/job_object.rs`).

**Why `PANTHER_PARENT_PID`:** inside the frozen process, `os.getppid()` returns the *bootloader*, not the Tauri app. When the app is force-killed without cascading termination, the bootloader survives, so a watchdog watching `os.getppid()` never fires. Passing the real app PID lets the watchdog observe the app disappearing. `resolve_watched_pid()` prefers the explicit PID and falls back to `os.getppid()`.

### CI Pipeline
`.github/workflows/tauri-windows.yml` (two jobs):

**`windows-tauri`** (`windows-latest`, 60 min):
1. Node 22, Rust stable, Python 3.12
2. `compileall` + per-suite pytest with `--timeout=120 --timeout-method=thread` (stage0, adapters, startup_adapter, integration, packaging, parent_watchdog, frozen entrypoint)
3. `python build_sidecar.py --clean`; verify `.exe` exists and size > 5 MB
4. **Frozen-binary smoke test**: pipe a JSON-RPC request via .NET `ProcessStartInfo` with UTF-8 encodings; stdout/stderr are drained asynchronously so a wedged child cannot consume the job timeout. Asserts exit 0 and stdout contains `"jsonrpc"` and `"result"`
5. Frontend `tsc --noEmit` + `npm run build`
6. `cargo check` + `cargo test`
7. `npx @tauri-apps/cli@2.12.4 build` (pinned) → NSIS installer
8. `build-summary.txt` (`if: always()`); artifacts: NSIS installer, sidecar binary, summary

**`installer-verify`** (needs `windows-tauri`):
1. Download installer; silent install via `Start-Process -Wait -PassThru`, asserting exit code 0
2. Locate app (fixed paths + recursive fallback); `ProgramFiles(x86)` read via `[System.Environment]::GetEnvironmentVariable`
3. Assert bundled sidecar is `panther-sidecar.exe` next to the app
4. Graceful shutdown: `CloseMainWindow()` + `WaitForExit(20000)`; assert no `panther-sidecar*` process
5. Forced kill: relaunch, `Stop-Process -Force`, poll up to 30 s for surviving sidecars, throw if any
6. Run uninstaller silently

`.github/workflows/ci.yml` (Windows matrix, Python 3.10 + 3.12) runs the sidecar suites per-file for fast failure attribution **and** a catch-all `pytest tests/` step so storage/UI/process suites are not dropped.

### Tests
- `tests/test_sidecar_packaging.py` — delivery-contract guards (42 passed)
- `tests/test_parent_watchdog.py` — pure helpers + injected loop + PID-resolution (24 passed)
- `tests/test_run_sidecar_entrypoint.py` — `PANTHER_PARENT_PID` parsing and frozen watchdog wiring (9 passed)
- `tests/test_sidecar_stage0.py` — stage 0 methods (15 passed)
- `tests/test_sidecar_adapters.py` — method adapters (36 passed)
- `tests/test_sidecar_integration.py` — end-to-end method calls (26 passed)
- `tests/test_startup_adapter.py` — registry error mapping across `FileNotFoundError` / plain `OSError` / `winreg is None` (10 passed)

---

## 2. Linux Verification (Per-Suite, at current working-tree state)

Each suite run separately with a hard outer timeout, mirroring CI flags.

| Test Suite | Result |
|---|---|
| `test_sidecar_stage0.py` | 15 passed |
| `test_sidecar_adapters.py` | 36 passed |
| `test_startup_adapter.py` | 10 passed |
| `test_sidecar_integration.py` | 26 passed |
| `test_sidecar_packaging.py` | 42 passed |
| `test_parent_watchdog.py` | 24 passed |
| `test_run_sidecar_entrypoint.py` | 9 passed |
| **Total** | **162 passed, 0 failed, 0 timeouts** |
| Catch-all `tests/` (CI coverage, excl. the 7 above) | 647 passed (with `QT_QPA_PLATFORM=offscreen`, PySide6 installed) |
| `python -m compileall -q src run_sidecar.py build_sidecar.py` | OK |
| Workflow YAML parse (`ci.yml`, `tauri-windows.yml`, `tauri-linux.yml`) | OK |

**Not verified locally:** the Rust code does not compile on this host (no glib/gtk dev libraries, no sudo). API usage was checked against the vendored crate source, but `cargo check` must pass on the Windows runner.

---

## 3. Windows CI — Previous Run Was Invalid

Run `43409175618` reported failures, but its `headSha` was `d22cd8a` while the fixes lived in `c4495cf` and `51e588f`, which had never been pushed. **Every rerun of that workflow re-ran the old code**, which is why the same failures repeated identically. That run is not evidence about the current tree.

Confirmed root causes behind that run, both fixed:

1. **`-32603` from startup methods.** `startup_adapter` caught only `PermissionError`; the HKLM Run key raises `FileNotFoundError`/plain `OSError` on the runner, which escaped to the server's generic handler. Fixed with `RegistryOperationError`, a per-scope `except OSError` inside the loop, and `_require_registry()` still fatal *before* the loop.
2. **Parent-watchdog test hang.** A test raised `StopIteration` from `is_alive`, which `parent_is_gone` swallowed as its safe default, producing an infinite loop. Fixed with a sentinel raised from the injected `sleep`.

---

## 4. Known Limitations (Unchanged, Out of Scope)

- No drive/volume enumeration; roots hardcoded to `C:\` in `adapters.py` and `storage.tsx`
- Startup **enable** raises `NotImplementedError` honestly; **disable** works
- Import-time DB writes: a locked/unwritable DB prevents sidecar start; data dir is cwd-independent (`%LOCALAPPDATA%`, `PANTHER_DATA_DIR`, `PANTHER_DB_PATH`)
- These are functional gaps, not packaging bugs

---

## 5. Continuation Path

### To produce real evidence

```bash
# Commit and push (requires explicit approval)
git add -A
git commit -m "fix(ci): correct Windows packaging, watchdog ownership and test coverage"
git push origin feature/storage-improvements
# Then watch the Tauri Windows CI run for this SHA
```

The workflow triggers on push to `feature/storage-improvements`.

### Expected first-run outcomes and what to do

1. **`windows-tauri` job** — runs the seven sidecar suites, builds the sidecar, runs the frozen-binary smoke test, builds the frontend, `cargo check`/`test`, builds NSIS, uploads artifacts.
2. **Likely remaining issues:**
   - **Rust compile errors** — the only genuinely unverified area locally. Any `set_process_group`/`env` type error surfaces here.
   - **Restored catch-all tests on Windows** — the 647 newly re-enabled tests were verified on Linux only. Windows-specific path or Qt-offscreen assumptions could fail; scope them with `--ignore` only if provably platform-specific, never to force green.
   - **`installer-verify` orphan assertions** — the watchdog and job-object fixes are designed for this but only a real Windows run proves it.
3. **Artifact verification** — download `panther-nsis-installer` and `panther-sidecar-binary`, check `build-summary.txt`.

### Manual Windows smoke test (per `docs/windows-delivery.md`)

On a clean Windows 10/11 VM **without Python installed**:

- [ ] NSIS installs without admin rights
- [ ] App launches; dashboard shows live CPU/RAM/Disk/Battery
- [ ] Processes, Storage (C:\), Applications, Startup, Settings all populate
- [ ] `panther-sidecar.exe` visible in Task Manager while running
- [ ] Closing the window terminates the sidecar within a few seconds
- [ ] Kill the app via Task Manager → sidecar disappears (watchdog reaps orphan)
- [ ] Uninstall leaves no running processes

---

## 6. File Map

```
run_sidecar.py                                  PyInstaller entrypoint
build_sidecar.py                                frozen build script
src/panther/sidecar/parent_watchdog.py          orphan prevention, owner-PID resolution
src/panther/sidecar/transport/stdio.py          UTF-8 stdio
src/panther/sidecar/server.py                   JSON-RPC error mapping
src/panther/services/startup_adapter.py         registry access + error mapping
src-tauri/tauri.conf.json                       externalBin / NSIS / currentUser
src-tauri/src/main.rs                           SidecarRef lifecycle, process group, PID
src-tauri/src/commands/metrics.rs               honest not-running error
.github/workflows/ci.yml                        test matrix + catch-all suite
.github/workflows/tauri-windows.yml             Windows packaging + installer verification
.github/workflows/tauri-linux.yml               Linux compile check
tests/test_sidecar_packaging.py                 delivery contract
tests/test_parent_watchdog.py                   watchdog unit tests
tests/test_run_sidecar_entrypoint.py            frozen entrypoint tests
tests/test_startup_adapter.py                   registry error mapping
tests/test_sidecar_adapters.py                  method adapters
tests/test_sidecar_stage0.py                    stage 0 methods
tests/test_sidecar_integration.py               end-to-end methods
docs/windows-delivery.md                        strategy + manual checklist
docs/windows-packaging-handoff.md               prior session handoff
```

---

## 7. Honest Status Table

| Stage | Status |
|-------|--------|
| Source code implemented | ✅ Complete |
| Linux unit / packaging tests | ✅ 162 passed + 647 catch-all |
| Workflow YAML valid | ✅ Parses |
| Rust compiles | ❓ Unverified locally (no GTK dev libs); Windows runner will decide |
| Frozen `.exe` built on Windows | ❓ Not yet proven for the current tree |
| Installer installs / app launches | ❓ Not yet proven |
| Orphan behaviour verified on Windows | ❓ Not yet proven |
| **Committed / pushed** | ❌ **No — awaiting approval** |
| **Windows CI passing** | ❌ **No** |

---

*Windows execution must be verified by the `windows-latest` runner. Linux checks are conclusive for source correctness only, not for Windows delivery.*
