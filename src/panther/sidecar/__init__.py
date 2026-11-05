"""Panther sidecar package.

A thin JSON-RPC 2.0 stdio sidecar that exposes existing
``src/panther.services`` functions to a Tauri frontend.  No backend
logic is duplicated or rewritten here.
"""

from .errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    SidecarError,
    error_response,
    success_response,
)
from .methods import call_method, has_method, list_methods

__all__ = [
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "METHOD_NOT_FOUND",
    "PARSE_ERROR",
    "SidecarError",
    "call_method",
    "error_response",
    "has_method",
    "list_methods",
    "success_response",
]
