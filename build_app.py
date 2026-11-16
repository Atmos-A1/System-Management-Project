#!/usr/bin/env python3
"""Build script for the Tauri + React production application.

This is the primary packaging path. The legacy PySide6 packaging via
`build_installer.py` is deprecated and retained only as a fallback.

Prerequisites (must be installed on the build machine):
- Node.js 20+ (LTS)
- Rust stable toolchain
- Tauri CLI (installed via `npm install` in src-tauri/frontend)
- Platform-specific Tauri prerequisites:
  - Linux: webkit2gtk-4.1, libayatana-appindicator3-dev, librsvg2-dev, etc.
  - Windows: Visual Studio Build Tools, WebView2 runtime
  - macOS: Xcode Command Line Tools

Usage:
    python build_app.py [--clean]

The script runs `tauri build` from the correct directory and reports
the output artifact locations.
"""

import sys
import os
import subprocess
import platform
import shutil
from pathlib import Path


def find_tauri_cli(frontend_dir: Path) -> Path | None:
    """Find the Tauri CLI binary in node_modules/.bin."""
    node_bin = frontend_dir / "node_modules" / ".bin"
    # Use shutil.which with explicit path — honours PATHEXT on Windows, PATH on POSIX
    tauri_cli = shutil.which("tauri", path=str(node_bin))
    if tauri_cli:
        return Path(tauri_cli)
    return None


def run_tauri_build(src_tauri_dir: Path, tauri_cli: Path, clean: bool) -> int:
    """Run `tauri build` from the src-tauri directory."""
    env = {**os.environ, "CI": "true"}
    if clean:
        env["TAURI_BUILD_CLEAN"] = "1"

    cmd = [str(tauri_cli), "build"]
    print(f"[build_app] Running: {' '.join(cmd)}")
    print(f"[build_app] Working directory: {src_tauri_dir}")

    try:
        result = subprocess.run(cmd, cwd=str(src_tauri_dir), env=env)
        return result.returncode
    except OSError as e:
        sys.stderr.write(
            f"ERROR: Failed to execute Tauri CLI: {e}\n"
            "Ensure the Tauri toolchain is installed.\n"
        )
        return 1


def find_output_artifacts(src_tauri_dir: Path) -> list[Path]:
    """Find the built installer/binary artifacts."""
    artifacts = []
    target_release = src_tauri_dir / "target" / "release"

    # NSIS installer (Windows)
    nsis_dir = target_release / "bundle" / "nsis"
    if nsis_dir.exists():
        artifacts.extend(nsis_dir.glob("*.exe"))

    # AppImage / deb / rpm (Linux)
    for bundle_type in ("appimage", "deb", "rpm"):
        bundle_dir = target_release / "bundle" / bundle_type
        if bundle_dir.exists():
            artifacts.extend(bundle_dir.glob("*"))

    # macOS .app / .dmg
    macos_dir = target_release / "bundle" / "macos"
    if macos_dir.exists():
        artifacts.extend(macos_dir.glob("*"))

    # Raw binary (all platforms) — Cargo package name is panther-tauri
    system = platform.system().lower()
    if system == "windows":
        binary_name = "panther-tauri.exe"
    else:
        binary_name = "panther-tauri"
    binary_path = target_release / binary_name
    if binary_path.exists():
        artifacts.append(binary_path)

    return artifacts


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    frontend_dir = repo_root / "src-tauri" / "frontend"
    src_tauri_dir = repo_root / "src-tauri"

    # Check prerequisites
    tauri_cli = find_tauri_cli(frontend_dir)
    if not tauri_cli:
        sys.stderr.write(
            "ERROR: Tauri CLI not found.\n"
            f"Expected at: {frontend_dir}/node_modules/.bin/tauri\n"
            "Run `npm install` in src-tauri/frontend first.\n"
        )
        return 1

    # Parse arguments
    clean = "--clean" in sys.argv

    # Run the build
    exit_code = run_tauri_build(src_tauri_dir, tauri_cli, clean)
    if exit_code != 0:
        sys.stderr.write(f"[build_app] Tauri build failed with exit code {exit_code}\n")
        return exit_code

    # Report artifacts
    artifacts = find_output_artifacts(src_tauri_dir)
    if artifacts:
        print("\n[build_app] Build successful. Artifacts:")
        for artifact in artifacts:
            size_mb = artifact.stat().st_size / (1024 * 1024)
            print(f"  {artifact} ({size_mb:.1f} MB)")
    else:
        print("\n[build_app] Build completed but no artifacts found in expected locations.")
        print(f"  Check: {src_tauri_dir}/target/release/bundle/")

    return 0


if __name__ == "__main__":
    sys.exit(main())