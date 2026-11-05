"""Method registry for the Panther sidecar.

Each entry is a thin wrapper around an existing ``src/panther/services``
function. No backend logic is duplicated or rewritten here.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from ...services import system_monitor


# Method name -> callable.  Signatures match the underlying service
# functions exactly; kwargs are forwarded from the JSON-RPC params.
METHODS: Dict[str, Callable[..., Any]] = {
    "system_monitor.get_cpu_percent": system_monitor.get_cpu_percent,
    "system_monitor.get_ram_usage": system_monitor.get_ram_usage,
    "system_monitor.get_disk_usage": system_monitor.get_disk_usage,
    "system_monitor.get_battery_info": system_monitor.get_battery_info,
}


def list_methods() -> list[str]:
    """Return the sorted list of available JSON-RPC method names."""
    return sorted(METHODS.keys())


def has_method(name: str) -> bool:
    """Return ``True`` if *name`` is a registered method."""
    return name in METHODS


def call_method(name: str, **kwargs) -> Any:
    """Call a registered method with the given keyword arguments.

    Raises :class:`KeyError` if the method is not registered.  Any
    exception raised by the underlying service function propagates to
    the caller (the server layer converts it to a JSON-RPC error).
    """
    fn = METHODS[name]
    return fn(**kwargs)
