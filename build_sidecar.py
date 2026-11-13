#!/usr/bin/env python3
"""Deterministic PyInstaller build script for the Panther sidecar.

Builds a single-file executable with the correct hidden imports and exclusions.
The output is renamed to include the target triple for Tauri's externalBin lookup.

Usage:
    python build_sidecar.py [--clean] [--target-triple TRIPLE] [--output-dir DIR]

Defaults:
    --target-triple: auto-detect (x86_64-pc-windows-msvc on Windows x64,
                     x86_64-unknown-linux-gnu on Linux x64)
    --output-dir: src-tauri/binaries
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def detect_target_triple() -> str:
    """Detect the host target triple for naming the output binary."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows" and machine in ("amd64", "x86_64"):
        return "x86_64-pc-windows-msvc"
    if system == "linux" and machine in ("x86_64", "amd64"):
        return "x86_64-unknown-linux-gnu"
    if system == "darwin" and machine in ("x86_64", "amd64"):
        return "x86_64-apple-darwin"
    if system == "darwin" and machine in ("arm64", "aarch64"):
        return "aarch64-apple-darwin"

    # Fallback
    return f"{machine}-unknown-{system}"


def run_pyinstaller(
    target_triple: str,
    output_dir: Path,
    clean: bool,
) -> Path:
    """Run PyInstaller and return the path to the built executable."""
    repo_root = Path(__file__).parent
    src_dir = repo_root / "src"
    entrypoint = repo_root / "run_sidecar.py"

    # Build directories (gitignored)
    distpath = repo_root / "build" / "sidecar-dist"
    workpath = repo_root / "build" / "sidecar-work"
    specpath = repo_root / "build" / "sidecar-spec"

    # Clean previous builds if requested
    if clean:
        for p in (distpath, workpath, specpath):
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)

    # Cross-compile guard: PyInstaller cannot cross-compile Windows binaries
    if target_triple.endswith("-windows-msvc") and platform.system().lower() != "windows":
        print(
            f"[build_sidecar] ERROR: PyInstaller cannot cross-compile Windows binaries from {platform.system()}; "
            f"run this on Windows",
            file=sys.stderr,
        )
        sys.exit(1)

    # PyInstaller command
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name",
        "panther-sidecar",
        "--paths",
        str(src_dir),
        "--distpath",
        str(distpath),
        "--workpath",
        str(workpath),
        "--specpath",
        str(specpath),
        "--hidden-import",
        "panther.services.directory_browser",
        "--hidden-import",
        "psutil._psutil_windows",
        "--exclude-module",
        "PySide6",
        "--exclude-module",
        "shiboken6",
        "--exclude-module",
        "pytest",
        "--exclude-module",
        "tkinter",
        str(entrypoint),
    ]

    print(f"[build_sidecar] Running PyInstaller for {target_triple}...")
    print(f"[build_sidecar] Command: {' '.join(cmd)}")

    # Stream output to console for CI visibility
    result = subprocess.run(cmd, cwd=repo_root)
    if result.returncode != 0:
        print(f"[build_sidecar] PyInstaller failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)

    # Locate the built executable
    exe_name = "panther-sidecar.exe" if target_triple.endswith("-windows-msvc") else "panther-sidecar"
    built_exe = distpath / exe_name

    if not built_exe.exists():
        # Sometimes the name differs slightly
        candidates = list(distpath.glob("panther-sidecar*"))
        if candidates:
            built_exe = candidates[0]
        else:
            print(f"[build_sidecar] ERROR: Built executable not found in {distpath}", file=sys.stderr)
            sys.exit(1)

    # Rename/copy to output directory with target triple
    output_dir.mkdir(parents=True, exist_ok=True)
    ext = ".exe" if target_triple.endswith("-windows-msvc") else ""
    final_name = f"panther-sidecar-{target_triple}{ext}"
    final_path = output_dir / final_name

    shutil.copy2(built_exe, final_path)

    # Verify size (bloat guard: >80 MB indicates accidental Qt inclusion)
    size_mb = final_path.stat().st_size / (1024 * 1024)
    if size_mb > 80:
        print(f"[build_sidecar] ERROR: Binary size {size_mb:.1f} MB exceeds 80 MB limit", file=sys.stderr)
        print("[build_sidecar] This likely indicates Qt/PySide6 was included accidentally.", file=sys.stderr)
        sys.exit(1)

    print(f"[build_sidecar] Success: {final_path} ({size_mb:.1f} MB)")
    return final_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Panther sidecar executable")
    parser.add_argument("--clean", action="store_true", help="Clean build directories before building")
    parser.add_argument("--target-triple", default=None, help="Target triple (default: auto-detect)")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: src-tauri/binaries)")
    args = parser.parse_args()

    target_triple = args.target_triple or detect_target_triple()
    output_dir = Path(args.output_dir) if args.output_dir else Path("src-tauri/binaries")

    if not output_dir.is_absolute():
        output_dir = Path(__file__).parent / output_dir

    print(f"[build_sidecar] Target triple: {target_triple}")
    print(f"[build_sidecar] Output directory: {output_dir}")

    final_path = run_pyinstaller(target_triple, output_dir, args.clean)
    print(f"[build_sidecar] Built: {final_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())