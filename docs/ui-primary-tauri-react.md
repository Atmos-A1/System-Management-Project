# UI Primary Path: Tauri 2 + React

**Status**: Tauri + React is the primary/default UI. PySide6 is retained as an explicitly labelled legacy fallback.

---

## Launch Paths

### Primary (Tauri + React)
| Command | Description |
|---------|-------------|
| `python run_panther.py` | Smart launcher: prefers built binary in `src-tauri/target/release/`, falls back to `tauri dev` |
| `cd src-tauri/frontend && npm run app:dev` | Direct `tauri dev` (hot reload) |
| `cd src-tauri/frontend && npm run app:build` | Direct `tauri build` (production) |
| `python build_app.py` | Wrapper script for production build with artifact reporting |

### Legacy (PySide6 / Qt)
| Command | Description |
|---------|-------------|
| `python run_panther_qt.py` | Legacy Qt entry point (exactly what `run_panther.py` used to do) |
| `python build_installer.py` | Legacy PyInstaller `--onedir` build (Windows only) |

---

## Development Workflow

```bash
# 1. Install frontend deps (includes @tauri-apps/cli@2.12.4)
cd src-tauri/frontend && npm install

# 2. Run dev mode (hot reload)
python run_panther.py
# or
cd src-tauri/frontend && npm run app:dev

# 3. Type-check + production build
cd src-tauri/frontend && npx tsc --noEmit && npm run build

# 4. Production build (requires Tauri prerequisites)
python build_app.py
```

---

## Configuration Changes Made

### `src-tauri/tauri.conf.json`
- `build.frontendDist`: `"../src-tauri/frontend/dist"` → `"frontend/dist"` (config-relative, robust)
- `build.beforeDevCommand`: `"npm run dev"` → `{ "script": "npm run dev", "cwd": "frontend" }` (object form)
- `build.beforeBuildCommand`: `"npm run build"` → `{ "script": "npm run build", "cwd": "frontend" }` (object form)

> The object form with `cwd` is supported by Tauri v2 schema (see `BeforeDevCommand` / `HookCommand` definitions). The `cwd` is relative to the project root (where `tauri.conf.json` lives, i.e., `src-tauri/`).

### `src-tauri/frontend/package.json`
- Added devDependency: `"@tauri-apps/cli": "^2.12.4"` (pinned to Windows workflow version)
- Added scripts:
  - `"app:dev": "cd .. && tauri dev"` — runs Tauri CLI from `src-tauri/` (where config lives)
  - `"app:build": "cd .. && tauri build"` — same, for production
- `npm` puts `node_modules/.bin` on PATH, so `tauri` resolves cross-shell (cmd, pwsh, bash, sh).

---

## Parity Gaps (React UI vs Legacy Qt)

**The following are NOT implemented in the React UI.** Buttons are disabled, flows incomplete, or features entirely missing. PySide6 stays in-tree until these are closed.

### Storage Tab
- [ ] Largest-file scan
- [ ] Duplicates detection & review UI
- [ ] Cleanup review (policy selection, dry-run, confirm)
- [ ] Metadata inspection (file details, extended attributes)
- [ ] Insights (charts, trends, breakdowns)
- [ ] Scan history (persisted, browsable)
- [ ] Progress + cancel during scan

### Startup Tab
- [ ] Re-enable flow (toggle → UAC prompt → registry write verification) — incomplete

### Settings Tab
- [ ] Side effects persistence (theme, notifications, scan intervals, etc.) — incomplete

### Security / Infra
- [ ] CSP: currently `null` in `tauri.conf.json` — hardening pending
- [ ] Frontend tests: none (unit, integration, e2e)

### Other
- [ ] Battery: advanced history/charts (basic works)
- [ ] Processes: some advanced actions (force-close confirmation, etc.)
- [ ] Applications: inventory export, bulk actions

---

## What Works in React UI (Verified)

- Dashboard: system metrics, sparklines, adaptive control panel
- Storage: disk-usage metric + single-directory listing/navigation (no scan, no filters)
- Processes: list, search, sort, basic actions (terminate)
- Applications: inventory list, search
- Battery: basic status, history (if implemented)
- Navigation, theming, design system components
- Sidecar IPC: JSON-RPC over stdio (CPU, memory, disk, processes, storage)

---

## CI / Acceptance

- **Windows acceptance**: `.github/workflows/tauri-windows.yml` — builds NSIS, installs silently, launches, verifies graceful/forced shutdown orphan cleanup. This is the gate for removing PySide6.
- **Linux CI**: `.github/workflows/tauri-linux.yml` — builds sidecar, frontend, `cargo build`. No full `tauri build` (webkit2gtk missing on this machine).

> **This machine cannot run `cargo build` or `tauri build`** — missing `webkit2gtk-4.1-dev` / `gtk+-3.0` dev packages. Frontend `tsc`/`vite build` and Python pytest work.

---

## Removal Criteria for PySide6

PySide6 (`run_panther_qt.py`, `build_installer.py`, `src/panther/ui/main_window.py`, etc.) will be deleted when:

1. All parity gaps above are implemented in React UI
2. Windows acceptance workflow passes (NSIS install + launch + orphan check)
3. CSP is configured and validated
4. Frontend test suite exists and passes

Until then, both UIs coexist. `run_panther.py` launches Tauri; `run_panther_qt.py` launches Qt.