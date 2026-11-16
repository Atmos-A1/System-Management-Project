"""Build script for creating a debuggable Windows executable using PyInstaller (LEGACY).

================================================================================
DEPRECATION NOTICE:
================================================================================
This script packages the LEGACY PySide6 UI. It is retained only as a fallback
until the Tauri + React UI reaches feature parity and passes Windows acceptance.

PRIMARY PACKAGING PATH:
- Use `build_app.py` which invokes the Tauri CLI to produce an NSIS installer.
- The Tauri workflow (`.github/workflows/tauri-windows.yml`) is the canonical
  release pipeline.

This legacy script will be removed once React UI parity is verified on Windows.
================================================================================

Strict specifications (legacy):
- --onedir
- --console (console output visible for diagnostics)
- --noupx (prevents Qt6 DLL corruption)
- --clean
- relative paths
"""

import subprocess
import sys
from pathlib import Path
import shutil

def main() -> None:
    print("=" * 78)
    print("WARNING: This script builds the LEGACY PySide6 UI (deprecated).")
    print("Primary packaging is now `python build_app.py` (Tauri + React + NSIS).")
    print("This legacy path will be removed after React UI parity on Windows.")
    print("=" * 78)

    project_root = Path(__file__).resolve().parent
    # Use the legacy Qt entry point explicitly
    entry_point = project_root / "run_panther_qt.py"
    
    if not entry_point.is_file():
        sys.exit(f"Legacy entry point not found: {entry_point}")

    # Clean previous build and dist to guarantee fresh compilation
    build_dir = project_root / "build"
    dist_dir = project_root / "dist"
    if build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)
    if dist_dir.exists():
        shutil.rmtree(dist_dir, ignore_errors=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--noupx",
        "--name", "PantherApp",
        "--paths", str(project_root / "src"),
        "--hidden-import", "PySide6.QtCore",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtWidgets",
        "--hidden-import", "PySide6.QtSvg",
        "--hidden-import", "PySide6.QtXml",
        "--hidden-import", "psutil",
        "--hidden-import", "send2trash",
        "--hidden-import", "sqlite3",
        str(entry_point),
    ]

    print("Running PyInstaller with: --onedir --console --noupx --clean ...")
    result = subprocess.run(cmd, cwd=str(project_root))
    if result.returncode != 0:
        sys.exit(f"PyInstaller failed with code {result.returncode}")

    target_exe = dist_dir / "PantherApp" / "PantherApp.exe"
    if not target_exe.is_file():
        sys.exit(f"Expected executable not found at: {target_exe}")

    print(f"\n[BUILD SUCCESS] Legacy executable created at: {target_exe}")
    print("NOTE: This is the LEGACY PySide6 build. Primary is `build_app.py`.")

if __name__ == "__main__":
    main()
