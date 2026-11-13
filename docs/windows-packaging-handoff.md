# Windows Packaging — Session Handoff

**Branch:** `feature/storage-improvements`
**Date:** 2026-11-13
**Status:** Implementation complete and verified to the limit of a Linux dev host. **Windows execution is NOT verified.** CI on `windows-latest` is the remaining proof.

---

## 1. Objective

Deliver Panther as an installable Windows 10/11 x64 Tauri 2 desktop app:

- Freeze the Python JSON-RPC sidecar into a standalone executable (no Python required on the target machine).
- Bundle it through Tauri `externalBin`.
- Provide a Windows CI + NSIS installer pipeline.
- Validate install → launch → sidecar spawn → live data → clean shutdown → no orphans.

**Never claim Windows delivery from Linux checks.** Only the `windows-latest` runner can prove freeze/install/launch/orphan behaviour.

---

## 2. What Was Implemented

### Sidecar freezing

| File | Purpose |
|------|---------|
| `run_sidecar.py` (new) | PyInstaller entrypoint. PyInstaller cannot freeze `-m panther.sidecar.server`, so this imports and calls `server.main()`. Reconfigures stdio to UTF-8 (Windows cp1252 would otherwise crash on non-ASCII process/path names). Starts the parent watchdog **only when `sys.frozen`**. |
| `build_sidecar.py` (new) | Deterministic PyInstaller build using CLI flags only (`*.spec` stays gitignored). Produces `src-tauri/binaries/panther-sidecar-<target-triple>.exe`. Hidden imports: `panther.services.directory_browser`, `psutil._psutil_windows`. Excludes PySide6/shiboken6/pytest/tkinter. Streams build output. 80 MB bloat guard. Cross-compile guard (refuses to build a Windows binary on Linux). |
| `src/panther/sidecar/parent_watchdog.py` (new) | Prevents orphaned sidecar processes when the app is force-killed. Pure helpers (`parent_is_gone`, `should_terminate`) plus `_watchdog_loop` with fully injected dependencies, so tests never spawn a thread that can `os._exit(0)` the test runner. `start_parent_watchdog` wires `os.getppid` / `psutil.pid_exists` / `time.sleep`. |
| `src/panther/sidecar/transport/stdio.py` | Added idempotent `configure_stdio()`: stdout/stderr UTF-8 `backslashreplace`, `\n` newlines, stdout line-buffered; stdin universal newlines. stdout remains protocol-only. |
| `src/panther/sidecar/server.py` | Calls `configure_stdio()` at startup so `python -m panther.sidecar.server` is also safe on Windows. EOF-on-stdin shutdown unchanged. |

**Packaging decision:** PyInstaller `--onefile --console`.
- `--console` is required for stdin/stdout pipe transport; `--windowed` would break JSON-RPC.
- **onedir rejected:** Tauri's `externalBin` copies files, not directories.
- **Nuitka rejected:** no MSVC toolchain on the build hosts and higher maintenance cost for a pure-Python sidecar whose only native dependency is `psutil`.

### Tauri lifecycle

| File | Change |
|------|--------|
| `src-tauri/tauri.conf.json` | `bundle.externalBin: ["binaries/panther-sidecar"]`, `bundle.targets: ["nsis"]`, `windows.nsis.installMode: "currentUser"` (no elevation). Hook commands and `frontendDist` deliberately unchanged — the CLI resolves the frontend dir to `src-tauri/frontend/`, where `package.json` lives. |
| `src-tauri/src/main.rs` | `SidecarRef = Arc<Mutex<Option<SidecarHandle>>>`. Bundled spawn sets `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, `PYTHONUNBUFFERED=1`; no `PYTHONPATH` (self-contained). Dev fallback keeps `PYTHONPATH` and gains the same env vars. **Spawn failure now logs diagnosis, manages state as `None`, and returns `Ok(())`** so the app still launches and commands surface an honest error instead of the app aborting. `CommandEvent::Terminated` takes the child out so later writes fail fast. |
| `src-tauri/src/commands/metrics.rs` | Uses `State<'_, SidecarRef>`; when the sidecar is absent returns: `system service is not running; Panther may not have installed correctly`. 10 s timeout and error mapping preserved. |
| `src-tauri/src/ipc/mod.rs`, `ipc/transport.rs` | Type alias and transport updated for the new ref; 4 MiB frame cap unchanged. |

### CI

`.github/workflows/tauri-windows.yml` (new), two jobs:

**`windows-tauri`** (`windows-latest`, 60 min):
1. Node 22 (npm cache), Rust stable, Python 3.12 (pip cache), `pip install -r requirements.txt pytest`.
2. `compileall` + sidecar test suites (`PYTHONPATH=src`).
3. `python build_sidecar.py --clean`; assert the exact `.exe` exists and is > 5 MB.
4. **Frozen-binary smoke test** using .NET `ProcessStartInfo` (redirected stdin/stdout/stderr, explicit UTF-8): sends `system_monitor.get_cpu_percent`, asserts exit 0 and stdout contains `"jsonrpc"` and `"result"`, dumps stderr on failure. This is the evidence the sidecar runs without Python.
5. Frontend `tsc --noEmit` + `npm run build`.
6. `cargo check` + `cargo test`.
7. `npx --yes @tauri-apps/cli@^2 build`; assert NSIS installer exists.
8. `build-summary.txt` (versions, paths, sizes) written in `if: always()`; artifacts: NSIS installer (`if-no-files-found: error`), sidecar binary, summary.

**`installer-verify`** (needs `windows-tauri`):
1. Download installer; silent install `/S`.
2. Locate app (fixed paths, then recursive fallback over `LOCALAPPDATA` / `PROGRAMFILES` / `PROGRAMFILES(x86)`).
3. Assert bundled sidecar is `panther-sidecar.exe` next to the app (triple-suffixed accepted as fallback). **Verified in tauri-bundler 2.6.1 `generate_binaries_data`:** the bundler strips `-<target-triple>` from the filename, so the installed name has no triple.
4. **Graceful shutdown:** launch, wait 15 s, `CloseMainWindow()`, `WaitForExit(20000)` (throws if it had to force), wait 3 s, assert no `panther-sidecar*` process.
5. **Forced-kill:** relaunch, wait 15 s, `Stop-Process -Force`, wait 5 s, assert no `panther-sidecar*` process (proves the watchdog).
6. Run the uninstaller silently.

### Tests and docs

- `tests/test_sidecar_packaging.py` — delivery-contract guards: files exist, UTF-8 stdout, watchdog only when frozen, PyInstaller flags, hidden imports, Qt exclusion, triple naming, `tauri.conf.json` bundle settings, Rust env vars / no `PYTHONPATH` in bundled branch, workflow YAML structure, `ProcessStartInfo`, **absence** of the broken `RedirectStandardInput $null`, `panther-sidecar.exe` in the locate step, `CloseMainWindow`, gitignore rules.
- `tests/test_parent_watchdog.py` — pure-helper and injected-loop tests; no real thread that can terminate pytest.
- `tests/test_sidecar_adapters.py`, `tests/test_sidecar_integration.py` — sidecar method coverage.
- `docs/windows-delivery.md` — strategy, artifact layout, CI steps, automated verification table, manual Windows checklist.

### Other

- `.gitignore`: added `build/sidecar-*/` and `src-tauri/binaries/`.
- `src-tauri/Cargo.lock` committed for reproducible Rust builds.

---

## 3. Verification Performed (Linux only)

| Check | Result |
|-------|--------|
| `pytest tests/test_sidecar_packaging.py` | 29 passed |
| `pytest tests/test_parent_watchdog.py` | 11 passed |
| `pytest tests/test_sidecar_stage0.py` | 15 passed |
| `pytest tests/test_sidecar_integration.py` | 26 passed |
| `python -m compileall -q src run_sidecar.py build_sidecar.py` | OK |
| YAML parse of `tauri-windows.yml` + JSON parse of `tauri.conf.json` | OK |
| `python build_sidecar.py --target-triple x86_64-pc-windows-msvc` on Linux | Exits 1 with cross-compile guard |
| Frontend `npx tsc --noEmit` + `npm run build` | Previously passed on this branch |

**Not run / impossible here:**
- `cargo check` / `cargo test` / `npx @tauri-apps/cli@^2 build` — Rust cannot compile on this host (`glib-sys` needs glib/gtk dev libraries; no sudo).
- PyInstaller freeze — no PyInstaller installed; only Python 3.14 is available and the repo venv does not include it.
- Any Windows install/launch/orphan test — no Windows runner.

---

## 4. Where We Stopped

Implementation and Linux-side verification are complete. The **only** remaining acceptance evidence is the Windows CI run:

1. `.github/workflows/tauri-windows.yml` has not been executed yet.
2. Therefore the following are **unproven**:
   - PyInstaller produces a working onefile `.exe` (~15–25 MB expected).
   - The frozen sidecar answers JSON-RPC without Python on PATH.
   - NSIS installs to `%LOCALAPPDATA%` without elevation.
   - Tauri finds and spawns `panther-sidecar.exe` after install.
   - Graceful close and forced kill leave no orphaned sidecar.
3. A known environment annoyance: running the whole pytest selection in one process occasionally truncates output on this host. Each suite passes individually; treat CI's summary line as authoritative.

---

## 5. Continuation Path

### Step 1 — Push and trigger CI

```bash
git push origin feature/storage-improvements
```

Then open **Actions → Tauri Windows CI → Run workflow** (`workflow_dispatch`) if the push does not trigger it.

### Step 2 — Read the first run

Expect the first `windows-tauri` run to surface environment issues rather than product bugs. Most likely candidates, in order:

1. **`pip install -r requirements.txt`** — the file contains GUI deps (PySide6) that are unnecessary here. If install is slow/fails, replace with a minimal install:
   `pip install psutil pyinstaller pytest pyyaml`.
2. **PyInstaller hidden imports** — if the smoke test errors on a missing module, add it to `build_sidecar.py` hidden imports (do not use `--collect-submodules panther`; it drags in Qt UI modules and trips the 80 MB guard).
3. **Tauri CLI hook cwd** — if `npm run build` fails with "package.json not found", pin the hook: `"beforeBuildCommand": { "script": "npm run build", "cwd": "frontend" }`. This should not be needed; the CLI resolves the frontend dir automatically.
4. **NSIS install path** — if discovery fails, print the installer's actual target directory in the CI log and extend the search list.
5. **`cargo test`** — if the Rust tests fail to compile, check that all `SidecarRef` call sites were updated.

### Step 3 — Verify the artifact

- Download `panther-nsis-installer` and `panther-sidecar-binary` artifacts.
- Check `build-summary.txt` for sidecar/installer sizes.

### Step 4 — Manual Windows smoke test

Run the checklist in `docs/windows-delivery.md` §"Manual Smoke-Test Checklist" on a clean Windows 10/11 VM **without Python installed**. Minimum acceptance:

- [ ] NSIS installs without admin rights.
- [ ] App launches; dashboard shows live CPU/RAM/Disk/Battery.
- [ ] Processes, Storage (drive list + directory browser), Applications, Startup, Settings all populate.
- [ ] `panther-sidecar.exe` visible in Task Manager while running.
- [ ] Closing the window terminates the sidecar within a few seconds.
- [ ] Kill the app via Task Manager → sidecar disappears within ~5 s (watchdog).
- [ ] Uninstall leaves no running processes.

### Step 5 — Known functional gaps (unchanged, out of scope for packaging)

- No drive/volume enumeration in the sidecar; roots are hardcoded to `C:\` in `src/panther/sidecar/methods/adapters.py` and `src-tauri/frontend/src/components/storage.tsx`. Storage will show only `C:\` on Windows.
- Enabled startup apps raise an honest `NotImplementedError` on startup enable; disable works.
- Import-time DB writes mean a locked/unwritable DB prevents sidecar start. Data dir resolution is cwd-independent (`%LOCALAPPDATA%`, `PANTHER_DATA_DIR`, `PANTHER_DB_PATH`).

---

## 6. Key Commands

```bash
# Local sidecar (dev, needs Python)
PYTHONPATH=src python -m panther.sidecar.server

# Build the frozen sidecar (Windows host only for a Windows binary)
python build_sidecar.py --clean

# Tests
PYTHONPATH=src python -m pytest -q tests/test_sidecar_packaging.py tests/test_parent_watchdog.py \
  tests/test_sidecar_stage0.py tests/test_sidecar_adapters.py tests/test_sidecar_integration.py

# Tauri desktop build (needs the sidecar artifact present)
npx --yes @tauri-apps/cli@^2 build
```

---

## 7. File Map

```
run_sidecar.py                                  PyInstaller entrypoint
build_sidecar.py                                frozen build script
src/panther/sidecar/parent_watchdog.py          orphan prevention
src/panther/sidecar/transport/stdio.py          UTF-8 stdio
src/panther/sidecar/server.py                   calls configure_stdio()
src-tauri/tauri.conf.json                       externalBin / NSIS / currentUser
src-tauri/src/main.rs                           SidecarRef lifecycle
src-tauri/src/commands/metrics.rs               honest not-running error
.github/workflows/tauri-windows.yml             CI pipeline
tests/test_sidecar_packaging.py                 delivery contract
tests/test_parent_watchdog.py                   watchdog unit tests
docs/windows-delivery.md                        strategy + manual checklist
docs/windows-packaging-handoff.md               this file
```
