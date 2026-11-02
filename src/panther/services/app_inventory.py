"""Application inventory service.

Provides functions to list installed applications from Windows registry
and other sources where available.
"""

from typing import List, Dict, Any
import winreg


def get_installed_apps() -> List[Dict[str, Any]]:
    """Return a list of installed applications."""
    apps: List[Dict[str, Any]] = []
    # Try to read from HKLM Uninstall keys
    uninstall_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    
    for root, subkey in uninstall_keys:
        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as key:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        i += 1
                        try:
                            with winreg.OpenKey(key, subkey_name) as app_key:
                                try:
                                    name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                except OSError:
                                    continue
                                try:
                                    publisher, _ = winreg.QueryValueEx(app_key, "Publisher")
                                except OSError:
                                    publisher = ""
                                try:
                                    version, _ = winreg.QueryValueEx(app_key, "DisplayVersion")
                                except OSError:
                                    version = ""
                                try:
                                    install_location, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                except OSError:
                                    install_location = ""
                                apps.append({
                                    "name": name,
                                    "publisher": publisher,
                                    "version": version,
                                    "install_location": install_location,
                                })
                        except OSError:
                            continue
                    except OSError:
                        break
        except (OSError, PermissionError):
            continue
    
    # Remove duplicates by name
    seen = set()
    unique_apps = []
    for app in apps:
        if app["name"] not in seen:
            seen.add(app["name"])
            unique_apps.append(app)
    
    return sorted(unique_apps, key=lambda x: x["name"].lower())
