"""stdio transport for the Panther sidecar.

Reads newline-delimited JSON-RPC 2.0 messages from stdin and writes
responses to stdout. Diagnostics go exclusively to stderr so the
protocol stream on stdout is never corrupted.
"""

from __future__ import annotations

import sys
from typing import Optional

MAX_FRAME_SIZE = 4 * 1024 * 1024  # 4 MiB


class FrameTooLargeError(Exception):
    """Raised when an input line exceeds the 4 MiB frame limit."""


def configure_stdio() -> None:
    """Reconfigure stdin/stdout/stderr for UTF-8 with safe error handling.

    On Windows, the default encoding is often cp1252, which causes
    UnicodeEncodeError when non-ASCII process names or paths appear in
    diagnostics. This sets UTF-8 with backslashreplace so such characters
    are escaped rather than crashing the process.

    Idempotent and safe to call multiple times. Cheap to import.
    """
    # stdin: ensure text mode with UTF-8, universal newlines (newline=None)
    if hasattr(sys.stdin, "reconfigure"):
        try:
            sys.stdin.reconfigure(encoding="utf-8", errors="backslashreplace", newline=None)
        except Exception:
            pass

    # stdout: protocol stream — UTF-8, line buffered, no error substitution on output
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(
                encoding="utf-8", errors="backslashreplace", newline="\n", line_buffering=True
            )
        except Exception:
            pass

    # stderr: diagnostics — UTF-8, backslashreplace for safety
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", newline="\n")
        except Exception:
            pass


def log_diagnostic(message: str) -> None:
    """Write a diagnostic message to stderr only.

    stdout is reserved exclusively for JSON-RPC protocol messages.
    """
    print(message, file=sys.stderr, flush=True)


def read_line() -> Optional[str]:
    """Read one line from stdin.

    Returns ``None`` on EOF. Raises :class:`FrameTooLargeError` if the
    line (including the newline) exceeds :data:`MAX_FRAME_SIZE`.
    """
    line = sys.stdin.readline()
    if line == "":
        return None
    if len(line.encode("utf-8")) > MAX_FRAME_SIZE:
        raise FrameTooLargeError(
            f"frame exceeds {MAX_FRAME_SIZE} bytes"
        )
    return line


def write_message(message: dict) -> None:
    """Write a JSON-RPC message as a single line to stdout.

    The message is serialized compactly (no trailing whitespace) and
    terminated with a newline. Flushes immediately so the Rust gateway
    never blocks waiting for a response.
    """
    import json

    line = json.dumps(message, separators=(",", ":"), ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def iter_lines():
    """Yield lines from stdin until EOF.

    Each yielded line has the trailing newline stripped. Raises
    :class:`FrameTooLargeError` on oversized frames.
    """
    while True:
        line = read_line()
        if line is None:
            return
        yield line.rstrip("\n").rstrip("\r")
