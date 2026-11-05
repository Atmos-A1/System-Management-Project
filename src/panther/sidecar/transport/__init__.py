"""stdio transport package for the Panther sidecar."""

from .stdio import (
    MAX_FRAME_SIZE,
    FrameTooLargeError,
    iter_lines,
    log_diagnostic,
    read_line,
    write_message,
)

__all__ = [
    "MAX_FRAME_SIZE",
    "FrameTooLargeError",
    "iter_lines",
    "log_diagnostic",
    "read_line",
    "write_message",
]
