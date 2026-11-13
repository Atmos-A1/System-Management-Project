"""Panther sidecar JSON-RPC 2.0 server loop.

Reads newline-delimited JSON-RPC 2.0 requests from stdin, dispatches
them to existing ``src/panther.services`` functions, and writes
responses to stdout.  Diagnostics go exclusively to stderr.
"""

from __future__ import annotations

import json
from typing import Optional

from .errors import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    SERVICE_UNAVAILABLE,
    SidecarError,
    error_response,
    success_response,
)
from .methods import call_method, has_method, list_methods
from .transport import FrameTooLargeError, log_diagnostic, read_line, write_message

# Import UnsupportedPlatformError from the startup adapter where it's defined
try:
    from ..services.startup_adapter import UnsupportedPlatformError
except ImportError:
    # Fallback if the import fails for any reason
    class UnsupportedPlatformError(RuntimeError):
        pass

# Shutdown flag set when the transport reports EOF or a fatal error.
_SHUTDOWN = False


def _handle_request(raw: str) -> Optional[dict]:
    """Parse and handle one JSON-RPC 2.0 message.

    Returns a response dict for requests (with ``id``), or ``None`` for
    notifications (without ``id``) and for parse errors where no id can
    be determined.
    """
    # 1. Parse JSON
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as exc:
        log_diagnostic(f"parse error: {exc}")
        return error_response(PARSE_ERROR, "Parse error", None, {"detail": str(exc)})

    # 2. Validate it's a JSON-RPC 2.0 object
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        log_diagnostic("invalid request: not a JSON-RPC 2.0 object")
        return error_response(INVALID_REQUEST, "Invalid Request", None)

    request_id = msg.get("id")
    method = msg.get("method")
    params = msg.get("params")

    # 3. Validate method
    if not isinstance(method, str):
        log_diagnostic("invalid request: missing or non-string method")
        return error_response(INVALID_REQUEST, "Invalid Request", request_id)

    # 4. Validate params (must be dict or absent)
    if params is not None and not isinstance(params, dict):
        log_diagnostic(f"invalid params for method {method!r}")
        return error_response(INVALID_PARAMS, "Invalid params", request_id)

    # 5. Check method exists
    if not has_method(method):
        log_diagnostic(f"method not found: {method}")
        return error_response(METHOD_NOT_FOUND, "Method not found", request_id)

    # 6. Call the method (may raise; caller catches)
    try:
        result = call_method(method, **(params or {}))
    except UnsupportedPlatformError as exc:
        # Platform-specific operations not supported on this OS
        log_diagnostic(f"unsupported platform in {method}: {exc}")
        return error_response(
            SERVICE_UNAVAILABLE,
            f"Unsupported on this platform: {exc}",
            request_id,
        )
    except NotImplementedError as exc:
        # Feature not implemented on this platform
        log_diagnostic(f"not implemented in {method}: {exc}")
        return error_response(
            SERVICE_UNAVAILABLE,
            f"Unsupported on this platform: {exc}",
            request_id,
        )
    except SidecarError as exc:
        log_diagnostic(f"sidecar error in {method}: {exc.message}")
        return error_response(exc.code, exc.message, request_id, exc.data)
    except ValueError as exc:
        # Validation errors from adapter functions (e.g., invalid threshold values)
        log_diagnostic(f"invalid params in {method}: {exc}")
        return error_response(INVALID_PARAMS, "Invalid params", request_id, {"detail": str(exc)})
    except Exception as exc:  # noqa: BLE001 - convert any service error to JSON-RPC
        log_diagnostic(f"internal error in {method}: {exc}")
        return error_response(INTERNAL_ERROR, "Internal error", request_id, {"detail": str(exc)})

    # 7. Notifications have no id and get no response
    if request_id is None:
        return None

    return success_response(request_id, result)


def main() -> None:
    """Run the sidecar stdio JSON-RPC loop until stdin closes."""
    global _SHUTDOWN

    # Configure stdio for UTF-8 safety on Windows (idempotent, cheap)
    from .transport.stdio import configure_stdio

    configure_stdio()

    log_diagnostic("panther sidecar starting")
    log_diagnostic(f"available methods: {', '.join(list_methods())}")

    while not _SHUTDOWN:
        try:
            raw = read_line()
        except FrameTooLargeError as exc:
            log_diagnostic(f"frame too large: {exc}")
            write_message(error_response(-32001, "Frame too large", None))
            continue
        except (OSError, ValueError) as exc:
            log_diagnostic(f"transport error: {exc}")
            break

        if raw is None:
            # EOF - clean shutdown
            log_diagnostic("stdin EOF, shutting down")
            break

        # Skip empty lines
        if not raw.strip():
            continue

        response = _handle_request(raw)
        if response is not None:
            write_message(response)

    log_diagnostic("panther sidecar stopped")


if __name__ == "__main__":
    main()