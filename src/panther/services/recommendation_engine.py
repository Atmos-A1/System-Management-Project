"""Recommendation engine service.

Generates evidence-based recommendations from system metrics.
"""

from typing import List, Dict, Any
from datetime import datetime


def get_recommendations(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []
    cpu = metrics.get("cpu_percent", 0)
    ram = metrics.get("ram_percent", 0)
    disk = metrics.get("disk_percent", 0)
    batt = metrics.get("battery_percent")
    
    if cpu > 80:
        recs.append({
            "issue": "High CPU usage",
            "evidence": f"CPU utilization at {cpu:.1f}%",
            "why": "High CPU usage can slow down your system and cause applications to lag.",
            "benefit": "Improved system responsiveness and faster application performance",
            "risk": "Closing critical processes may cause system instability or data loss",
            "action": "Review top CPU-consuming processes in the Processes tab and close safe ones",
            "confidence": 0.9,
            "impact": "High",
            "safety": "Medium",
            "category": "Performance",
        })
    
    if ram > 85:
        recs.append({
            "issue": "High memory pressure",
            "evidence": f"RAM usage at {ram:.1f}%",
            "why": "When RAM is nearly full, Windows uses disk swap which significantly slows performance.",
            "benefit": "Free up memory to reduce disk paging and improve speed",
            "risk": "Closing system services or critical apps may cause data loss or instability",
            "action": "Identify and close unnecessary applications using high memory",
            "confidence": 0.9,
            "impact": "High",
            "safety": "Medium",
            "category": "Performance",
        })
    
    if disk > 90:
        recs.append({
            "issue": "Low disk free space",
            "evidence": f"Disk usage at {disk:.1f}%",
            "why": "Running out of disk space can prevent updates, downloads, and normal system operation.",
            "benefit": "Prevent out-of-space errors and improve system stability",
            "risk": "Deleting files may remove important personal data",
            "action": "Use Storage tab to find and remove large files or duplicates",
            "confidence": 0.95,
            "impact": "Critical",
            "safety": "High (when using Recycle Bin)",
            "category": "Storage",
        })
    elif disk > 80:
        recs.append({
            "issue": "Disk space getting low",
            "evidence": f"Disk usage at {disk:.1f}%",
            "why": "Disk space is running low - good to clean up before it becomes critical.",
            "benefit": "Free up space for future use and updates",
            "risk": "Minimal if reviewing before deleting",
            "action": "Review large files and unnecessary downloads",
            "confidence": 0.85,
            "impact": "Medium",
            "safety": "High",
            "category": "Storage",
        })
    
    if batt is not None and batt < 20:
        recs.append({
            "issue": "Low battery",
            "evidence": f"Battery at {batt:.0f}%",
            "why": "Low battery can cause unexpected shutdowns and data loss.",
            "benefit": "Extend runtime and prevent unexpected shutdown",
            "risk": "Power saving mode may reduce performance",
            "action": "Plug in charger or enable power saving mode",
            "confidence": 0.95,
            "impact": "High",
            "safety": "High",
            "category": "Power",
        })
    
    # Sort by impact
    impact_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    recs.sort(key=lambda x: impact_order.get(x.get('impact', 'Low'), 3))
    
    return recs
