"""Build script for creating a debuggable Windows executable using PyInstaller.

Strict specifications:
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
    project_root = Path(__file__).resolve().parent
    entry_point = project_root / "run_panther.py"
    
    if not entry_point.is_file():
        sys.exit(f"Entry point not found: {entry_point}")

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
        "--hidden-import", "sqlite3",
        "--hidden-import", "send2trash",
        str(entry_point),
    ]

    print("Running PyInstaller with: --onedir --console --noupx --clean ...")
    result = subprocess.run(cmd, cwd=str(project_root))
    if result.returncode != 0:
        sys.exit(f"PyInstaller failed with code {result.returncode}")

    target_exe = dist_dir / "PantherApp" / "PantherApp.exe"
    if not target_exe.is_file():
        sys.exit(f"Expected executable not found at: {target_exe}")

    print(f"\n[BUILD SUCCESS] Executable created at: {target_exe}")

if __name__ == "__main__":
    main()
