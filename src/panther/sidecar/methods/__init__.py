"""Method registry for the Panther sidecar.

Each entry is a thin wrapper around an existing ``src/panther/services``
function or an adapter in ``src/panther/sidecar/methods/adapters``.
No backend logic is duplicated or rewritten here.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from ...services import system_monitor
from .adapters import (
    get_adaptive_control,
    get_activity_history,
    get_battery_info_with_status,
    get_disk_usage_platform,
    get_hostname,
    get_installed_applications,
    get_operating_system,
    get_processes,
    get_recommendations,
    get_settings,
    get_startup_apps,
    get_uptime,
    list_directory,
    set_adaptive_control,
    set_settings,
    set_startup_app_state,
)


# Method name -> callable.  Signatures match the underlying service
# functions exactly; kwargs are forwarded from the JSON-RPC params.
METHODS: Dict[str, Callable[..., Any]] = {
    # Existing Stage 0 methods
    "system_monitor.get_cpu_percent": system_monitor.get_cpu_percent,
    "system_monitor.get_ram_usage": system_monitor.get_ram_usage,
    "system_monitor.get_disk_usage": get_disk_usage_platform,
    "system_monitor.get_battery_info": get_battery_info_with_status,
    # New methods for real backend integration
    "system_monitor.uptime": get_uptime,
    "system_monitor.operating_system": get_operating_system,
    "system_monitor.hostname": get_hostname,
    "system_monitor.get_processes": get_processes,
    "system_monitor.get_recommendations": get_recommendations,
    "system_monitor.get_activity_history": get_activity_history,
    "system_monitor.get_startup_apps": get_startup_apps,
    "system_monitor.set_startup_app_state": set_startup_app_state,
    "system_monitor.get_installed_applications": get_installed_applications,
    "system_monitor.get_adaptive_control": get_adaptive_control,
    "system_monitor.set_adaptive_control": set_adaptive_control,
    "system_monitor.get_settings": get_settings,
    "system_monitor.set_settings": set_settings,
    "system_monitor.list_directory": list_directory,
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