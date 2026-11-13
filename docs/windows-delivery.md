# Windows Delivery — Panther Sidecar Packaging

## Chosen Strategy: PyInstaller Onefile

**Why PyInstaller onefile over Nuitka/onedir?**

| Criterion | PyInstaller Onefile | Nuitka Onefile | Onedir (any) |
|-----------|---------------------|----------------|--------------|
| Startup latency | ~0.5–2 s on first launch (self-extraction) | ~100–200 ms (compiled) | ~50 ms (no extract) |
| Binary size | ~15–25 MB | ~10–15 MB | ~50–100 MB (folder) |
| Windows compatibility | Excellent (mature) | Good (improving) | Excellent |
| Stdout/stdin piping | Works with `--console` | Works | Works |
| Tauri `externalBin` | Native support | Native support | Requires folder bundling |
| Hidden import control | Explicit CLI flags | Auto-detection (harder to control) | Same |
| Qt exclusion | `--exclude-module` works | Requires `--nofollow-imports` | Same |
| Maintenance burden | Low (standard in repo) | Higher (separate toolchain) | Higher (folder sync) |

**Decision**: PyInstaller onefile with `--console` is the pragmatic choice. The startup latency is acceptable for a background sidecar, the binary size stays well under the 80 MB bloat guard, and Tauri's `externalBin` lookup (`panther-sidecar.exe` after bundle-time triple stripping) maps directly to our renamed output. Nuitka's compilation benefits don't outweigh the added toolchain complexity for a pure-Python sidecar with only `psutil` as a native dependency.

---

## Artifact Layout

```
repo-root/
├── run_sidecar.py              # PyInstaller entrypoint (UTF-8 stdio, parent watchdog)
├── build_sidecar.py            # Deterministic build script (CLI flags only)
├── src/
│   └── panther/
│       └── sidecar/
│           ├── parent_watchdog.py   # Orphan prevention daemon thread
│           ├── server.py            # JSON-RPC stdio server (calls configure_stdio)
│           └── transport/stdio.py   # configure_stdio() implementation
├── src-tauri/
│   ├── binaries/                       # GITIGNORED — built artifacts
│   │   └── panther-sidecar-x86_64-pc-windows-msvc.exe
│   ├── tauri.conf.json                 # externalBin, targets: ["nsis"], currentUser
│   └── src/
│       ├── main.rs                     # SidecarRef, env vars, graceful failure
│       └── commands/metrics.rs         # Honest "not running" error
└── .github/workflows/tauri-windows.yml  # CI: build → smoke test → NSIS → installer verify
```

**Note**: The triple-suffixed name (`panther-sidecar-x86_64-pc-windows-msvc.exe`) exists only in `src-tauri/binaries/`. Tauri's bundler strips the `-<target-triple>` suffix at bundle time, so the installed file next to the app is `panther-sidecar.exe`.

---

## How CI Builds It

**Workflow**: `.github/workflows/tauri-windows.yml`

### Job `windows-tauri` (runs-on `windows-latest`)

1. **Setup**: Node 22, Rust stable, Python 3.12
2. **Python tests**: `compileall` + `pytest` (stage0, adapters, integration, packaging, parent_watchdog)
3. **Build sidecar**: `python build_sidecar.py --clean`
   - Output: `src-tauri/binaries/panther-sidecar-x86_64-pc-windows-msvc.exe`
   - Size assertion: > 5 MB, < 80 MB
4. **Smoke test (critical)**: Pipe JSON-RPC request into frozen exe **without Python on PATH** using `ProcessStartInfo` with redirected stdin/stdout/stderr
   Asserts: exit code 0, stdout contains `"jsonrpc"` and `"result"`
5. **Frontend**: `tsc --noEmit` + `npm run build`
6. **Rust**: `cargo check` + `cargo test`
7. **Tauri build**: `npx --yes @tauri-apps/cli@^2 build` → NSIS installer
8. **Build summary**: write `build-summary.txt` (ref/branch, Python/Node/Rust versions, sidecar path+size, installer path+size)
9. **Artifacts**: NSIS installer, sidecar binary, build summary

### Job `installer-verify` (needs `windows-tauri`)

1. Download installer artifact
2. Silent install: `installer.exe /S`
3. Locate installed app + bundled sidecar (AppData or ProgramFiles, with recursive fallback search)
   - Installed sidecar is `panther-sidecar.exe` (Tauri strips triple at bundle time)
   - Fallback to triple-suffixed name if present
4. **Graceful shutdown orphan check**: Launch app, wait 15s, `CloseMainWindow()`, `WaitForExit(20000)`, wait 3s, assert no `panther-sidecar*` processes
5. **Forced kill orphan check**: Relaunch app, wait 15s, `Stop-Process -Force`, wait 5s, assert no `panther-sidecar*` processes
6. Run uninstaller silently

---

## Automated Windows Verification Steps

| Step | What It Proves |
|------|----------------|
| `python -m pytest tests/test_sidecar_packaging.py` | All delivery contracts present in source |
| `python build_sidecar.py --clean` | Deterministic onefile build succeeds |
| Size check (>5 MB, <80 MB) | No Qt bloat, binary is substantial |
| Smoke test (frozen exe, no Python, `ProcessStartInfo`) | Sidecar runs independently, JSON-RPC works |
| `cargo test` | Rust sidecar management logic correct |
| Tauri NSIS build | Installer produces correctly bundled app |
| Installer silent install | Real Windows install succeeds |
| App launch + 15s run | Sidecar spawns, communicates with app |
| **Graceful shutdown orphan check** | `CloseMainWindow` + watchdog prevents zombies |
| **Forced kill orphan check** | Watchdog reaps sidecar after forced app termination |
| Uninstall clean | No residue |

**Note**: The automated job proves install, launch, sidecar spawn, clean shutdown (graceful and forced), and no-orphan. Real data rendering (dashboard, processes, storage tabs) is covered by the manual checklist only — process liveness does not prove data correctness.

---

## Manual Smoke-Test Checklist

Run on a clean Windows 10/11 machine (VM or physical) **without Python installed**.

### 1. Install
- [ ] Download NSIS installer from CI artifact or local build
- [ ] Run installer silently: `Panther-System-Intelligence_0.1.0_x64_en-US.exe /S`
- [ ] Verify installed at `%LOCALAPPDATA%\Panther System Intelligence\` (currentUser mode)

### 2. Launch
- [ ] Start app from Start Menu or executable
- [ ] Window opens, no crash dialog
- [ ] Dashboard loads: CPU %, RAM, Disk, Battery cards show live data
- [ ] Processes tab: list populates, sortable, searchable
- [ ] Storage tab: drive list shows, directory browser works (navigate C:\)
- [ ] Applications tab: installed apps list (may be empty on clean VM)
- [ ] Startup tab: startup entries listed (enable/disable works)
- [ ] Settings: theme toggle, notifications, language persist after restart

### 3. Sidecar Verification
- [ ] Open Task Manager → Details → verify `panther-sidecar.exe` running
- [ ] Sidecar stderr diagnostics visible in console (if launched from cmd) or captured in logs
- [ ] No `python.exe` processes (proves frozen binary used)

### 4. Storage / Drive Paths
- [ ] Directory browser: navigate `C:\Users`, `C:\Windows`, `D:\` (if exists)
- [ ] No crashes on reparse points, hidden files, permission denied
- [ ] Size columns show plausible values

### 5. Directory Browsing
- [ ] Click into folders, breadcrumb navigation works
- [ ] "Up" button works
- [ ] Large folders load incrementally (no UI freeze)

### 6. Installed Applications
- [ ] List populates (name, version, publisher)
- [ ] Uninstall buttons present (may not function on clean VM)

### 7. Startup Apps
- [ ] List shows current user + machine entries
- [ ] Disable toggle works (entry removed from registry)
- [ ] Enable shows honest "not implemented" error (toast)

### 8. Settings Persistence
- [ ] Change theme to Dark, restart app → theme is Dark
- [ ] Toggle notifications off, restart → stays off
- [ ] Language change persists

### 9. Clean Shutdown / No Orphans
- [ ] Close app window (X button)
- [ ] Wait 3 seconds
- [ ] Task Manager: **no `panther-sidecar*` processes remain**
- [ ] No "Python has stopped working" dialogs

### 10. Honest Unsupported States
- [ ] On Windows: all tabs functional
- [ ] If any feature unavailable: toast/error shows "not supported on this platform" not generic crash
- [ ] Startup Apps "Enable" shows specific "not implemented" message

### 11. Uninstall
- [ ] Run uninstaller: `%LOCALAPPDATA%\Panther System Intelligence\uninstall.exe /S`
- [ ] App removed from Start Menu
- [ ] Installation folder removed
- [ ] No orphaned processes after uninstall

---

## Critical Implementation Notes

### Stdout/Stderr Discipline
- **stdout**: JSON-RPC protocol **only** — never write diagnostics here
- **stderr**: All diagnostics, logs, tracebacks
- Both reconfigured to UTF-8 with `backslashreplace` on Windows (fixes cp1252 crashes)
- **stdin**: `newline=None` (universal newlines), **stdout/stderr**: `newline="\n"`, stdout `line_buffering=True`

### Parent Watchdog
- Runs **only when frozen** (`sys.frozen`)
- Daemon thread polls `os.getppid()` every 2s
- On parent death: `os._exit(0)` (immediate, no cleanup)
- Safe: swallows all errors, no-op if `psutil` missing
- Testable: `_watchdog_loop` and `parent_is_gone` are pure functions with injected collaborators

### Tauri Sidecar Management
- `SidecarRef = Arc<Mutex<Option<SidecarHandle>>>`
- Always managed — `Some` on success, `None` on failure
- Commands return honest error: `"system service is not running; Panther may not have installed correctly"`
- On `Terminated` event: `child.take()` so subsequent writes fail fast
- Env vars: `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, `PYTHONUNBUFFERED=1`
- **No `PYTHONPATH` in bundled branch** (self-contained)
- Production spawn failure: manages state, logs clear stderr diagnosis, returns `Ok(())` so app launches

### Build Script Guards
- `--exclude-module PySide6 shiboken6 pytest tkinter`
- **No `--collect-submodules panther`** (would drag Qt)
- **No `--windowed`** (breaks stdin/stdout pipes)
- Size check: fail if > 80 MB
- Missing exe: fail with clear path
- Cross-compile guard: fails if targeting Windows from non-Windows host

---

## Verification Scope

**Linux CI can verify:**
- Source contracts (packaging tests)
- Python syntax (`compileall`)
- Unit tests (stage0, adapters, parent_watchdog)
- Rust `cargo check` / `cargo test`
- Frontend `tsc` / `npm run build`

**Linux CI CANNOT verify:**
- PyInstaller frozen binary execution
- NSIS installer behavior
- Windows process spawning / orphan cleanup
- Windows-specific path handling (C:\, reparse points)
- Actual sidecar JSON-RPC over stdio on Windows

**Windows runner is mandatory** for the smoke test, installer verify, and orphan checks (graceful + forced). Do not assume Linux success implies Windows correctness.