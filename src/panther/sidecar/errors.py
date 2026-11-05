"""JSON-RPC 2.0 error codes and helpers for the Panther sidecar.

These codes follow the JSON-RPC 2.0 specification
(https://www.jsonrpc.org/specification#error_object).
"""

# Standard JSON-RPC 2.0 error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Sidecar-specific reserved range: -32000 to -32099
SERVICE_UNAVAILABLE = -32000
FRAME_TOO_LARGE = -32001


class SidecarError(Exception):
    """Base class for sidecar errors with an associated JSON-RPC code."""

    def __init__(self, code: int, message: str, data: object = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def error_response(code: int, message: str, request_id: object = None, data: object = None) -> dict:
    """Build a JSON-RPC 2.0 error response object."""
    err: dict = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": err}


def success_response(request_id: object, result: object) -> dict:
    """Build a JSON-RPC 2.0 success response object."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}
