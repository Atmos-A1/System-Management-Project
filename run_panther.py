#!/usr/bin/env python3
"""Primary launcher for Panther System Intelligence (Tauri + React).

This is the primary UI launch path. The legacy PySide6 UI is available
via `run_panther_qt.py`.

Launch strategy:
1. Prefer an already-built local binary in `src-tauri/target/release/`
2. Fall back to running `tauri dev` via the Tauri CLI (requires Node.js, Rust, and Tauri toolchain)

The script resolves all paths from __file__ so it works from any CWD.
"""

import sys
import os
import subprocess
import platform
import shutil
from pathlib import Path


def find_built_binary() -> Path | None:
    """Find a built Tauri binary in target/release/ if it exists."""
    repo_root = Path(__file__).resolve().parent
    target_release = repo_root / "src-tauri" / "target" / "release"

    if not target_release.exists():
        return None

    system = platform.system().lower()
    if system == "windows":
        # On Windows, the binary is typically named after productName with spaces removed or as panther-tauri.exe
        candidates = [
            target_release / "Panther System Intelligence.exe",
            target_release / "panther-tauri.exe",
            target_release / "panther-system-intelligence.exe",
        ]
    else:
        # On Linux/macOS, the binary is typically the productName lowercased with dashes
        candidates = [
            target_release / "panther-system-intelligence",
            target_release / "panther-tauri",
            target_release / "Panther System Intelligence",
        ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    return None


def run_tauri_dev() -> int:
    """Run `tauri dev` from the src-tauri directory via the frontend's node_modules/.bin."""
    repo_root = Path(__file__).resolve().parent
    frontend_dir = repo_root / "src-tauri" / "frontend"
    node_bin = frontend_dir / "node_modules" / ".bin"

    # Use shutil.which with explicit path — honours PATHEXT on Windows, PATH on POSIX
    tauri_cli = shutil.which("tauri", path=str(node_bin))

    if not tauri_cli:
        sys.stderr.write(
            "ERROR: Tauri CLI not found at expected location.\n"
            "Expected: src-tauri/frontend/node_modules/.bin/tauri\n"
            "Run `npm install` in src-tauri/frontend to install the Tauri CLI.\n"
        )
        return 1

    # Run tauri dev from src-tauri directory (where tauri.conf.json lives)
    src_tauri_dir = repo_root / "src-tauri"
    try:
        # Forward any CLI args (e.g., --help) to tauri dev
        result = subprocess.run(
            [tauri_cli, "dev", *sys.argv[1:]],
            cwd=str(src_tauri_dir),
            env={**os.environ, "TAURI_ENV_DEBUG": "1"},
        )
        return result.returncode
    except OSError as e:
        sys.stderr.write(
            f"ERROR: Failed to execute Tauri CLI: {e}\n"
            "Ensure Node.js and the Tauri toolchain are installed.\n"
        )
        return 1


def run_built_binary(binary_path: Path) -> int:
    """Run the built Tauri binary directly."""
    try:
        result = subprocess.run([str(binary_path)])
        return result.returncode
    except FileNotFoundError:
        sys.stderr.write(f"ERROR: Binary not found: {binary_path}\n")
        return 1
    except PermissionError:
        sys.stderr.write(f"ERROR: Permission denied executing: {binary_path}\n")
        return 1


def main() -> int:
    # First, try to find and run a built binary
    binary = find_built_binary()
    if binary:
        print(f"[launcher] Found built binary: {binary}")
        return run_built_binary(binary)

    # Fall back to tauri dev
    print("[launcher] No built binary found; starting `tauri dev`...")
    return run_tauri_dev()


if __name__ == "__main__":
    sys.exit(main())