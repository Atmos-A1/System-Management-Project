#!/usr/bin/env python3
"""PyInstaller entrypoint for the Panther sidecar.

Cannot freeze `python -m panther.sidecar.server`, so this script serves as the
onefile entrypoint. It configures stdio for Windows UTF-8 safety, optionally
starts the parent watchdog when frozen, and delegates to the server main().
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _insert_src_path() -> None:
    """Insert the src directory into sys.path when not frozen.

    This allows `python run_sidecar.py` to work for local testing without
    requiring the package to be installed or PYTHONPATH to be set.
    """
    if not getattr(sys, "frozen", False):
        src_dir = Path(__file__).parent / "src"
        if src_dir.exists():
            sys.path.insert(0, str(src_dir))


def configure_stdio() -> None:
    """Reconfigure stdin/stdout/stderr for UTF-8 with safe error handling.

    Delegates to the single implementation in stdio.py to avoid duplication.
    """
    from panther.sidecar.transport.stdio import configure_stdio as _configure_stdio

    _configure_stdio()


def _start_parent_watchdog_if_frozen() -> None:
    """Start the parent watchdog thread when running as a frozen PyInstaller executable.

    The watchdog ensures the sidecar exits cleanly if the Tauri parent process
    is killed (preventing orphaned onefile child processes).
    """
    if getattr(sys, "frozen", False):
        try:
            from panther.sidecar.parent_watchdog import start_parent_watchdog

            start_parent_watchdog(interval=2.0)
        except Exception:
            # Never fail startup due to watchdog issues
            pass


def main() -> int:
    """Run the sidecar server, returning an exit code."""
    _insert_src_path()
    configure_stdio()
    _start_parent_watchdog_if_frozen()

    try:
        from panther.sidecar.server import main as server_main

        server_main()
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())