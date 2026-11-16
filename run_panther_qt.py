#!/usr/bin/env python3
"""Legacy PySide6 UI entry point for Panther System Intelligence.

This is the legacy Qt-based UI. The primary UI is now Tauri + React.
This file is kept for fallback and parity verification until the React UI
reaches feature parity and passes Windows acceptance testing.

DO NOT DELETE: Used for comparison testing and as a fallback launch path.
"""

import sys
import os
from pathlib import Path

# Ensure src is on sys.path for development and execution
src_path = str(Path(__file__).resolve().parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from panther.main import main

if __name__ == "__main__":
    sys.exit(main())