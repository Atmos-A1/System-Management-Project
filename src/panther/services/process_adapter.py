"""Process service adapters.

Provides a wrapper around ``psutil`` to fetch the current process list with
detailed information for process management and analysis.
"""

try:
    import psutil
except Exception:
    psutil = None

import os
from typing import List, Dict, Any
from datetime import datetime


def get_processes() -> List[Dict[str, Any]]:
    """Return a list of running processes with detailed attributes."""
    if psutil is None:
        raise RuntimeError("psutil is required for process enumeration")
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 
                                   'ppid', 'exe', 'cmdline', 'username', 
                                   'create_time', 'status']):
        try:
            info = p.info
            mem_info = info.get("memory_info")
            create_time = info.get("create_time")
            start_time = None
            if create_time:
                try:
                    start_time = datetime.fromtimestamp(create_time).strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    start_time = None
            
            exe_path = info.get("exe") or ""
            cmdline = info.get("cmdline") or []
            cmdline_str = " ".join(cmdline) if cmdline else ""
            
            memory_rss = 0
            memory_vms = 0
            if mem_info:
                memory_rss = getattr(mem_info, 'rss', 0) or 0
                memory_vms = getattr(mem_info, 'vms', 0) or 0
            
            procs.append({
                "pid": info.get("pid"),
                "ppid": info.get("ppid"),
                "name": info.get("name") or "",
                "exe": exe_path,
                "cmdline": cmdline_str,
                "username": info.get("username") or "",
                "cpu_percent": float(info.get("cpu_percent") or 0.0),
                "memory_rss": memory_rss,
                "memory_vms": memory_vms,
                "status": info.get("status") or "",
                "create_time": create_time,
                "start_time": start_time,
            })
        except Exception:
            # Skip processes that can't be accessed
            continue
    return procs


def get_process_tree() -> tuple:
    """Build a process tree structure grouped by parent PID."""
    procs = get_processes()
    tree = {}
    proc_map = {p['pid']: p for p in procs}
    
    for proc in procs:
        ppid = proc.get('ppid', 0) or 0
        if ppid not in tree:
            tree[ppid] = []
        tree[ppid].append(proc)
    
    return tree, proc_map


def get_process_details(pid: int) -> Dict[str, Any]:
    """Get detailed information for a specific process."""
    if psutil is None:
        raise RuntimeError("psutil is required")
    try:
        p = psutil.Process(pid)
        mem_info = p.memory_info()
        create_time = p.create_time()
        start_time = None
        if create_time:
            try:
                start_time = datetime.fromtimestamp(create_time).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                start_time = None
        
        exe = ""
        try:
            exe = p.exe()
        except Exception:
            exe = ""
        
        cmdline = ""
        try:
            if p.cmdline():
                cmdline = " ".join(p.cmdline())
        except Exception:
            cmdline = ""
        
        username = ""
        try:
            username = p.username()
        except Exception:
            username = ""
        
        cwd = ""
        try:
            cwd = p.cwd()
        except Exception:
            cwd = ""
        
        return {
            "pid": p.pid,
            "ppid": p.ppid(),
            "name": p.name(),
            "exe": exe,
            "cmdline": cmdline,
            "username": username,
            "cpu_percent": p.cpu_percent(interval=0.1),
            "memory_rss": mem_info.rss,
            "memory_vms": mem_info.vms,
            "status": p.status(),
            "create_time": create_time,
            "start_time": start_time,
            "num_threads": p.num_threads(),
            "cwd": cwd,
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        raise
