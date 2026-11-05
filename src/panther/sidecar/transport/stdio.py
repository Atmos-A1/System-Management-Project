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
