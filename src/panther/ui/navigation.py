"""Navigation definitions for the sidebar.
Provides a constant ``NAV_ITEMS`` – a list of tuples ``(name, icon_path)``.
Icons are optional; we use placeholder empty strings for now.
"""

# Order matters – used by ``MainWindow`` to build the sidebar
# Per PRD section 6.2: Dashboard, Processes, Storage, Battery, Startup Apps, 
# Applications, Recommendations, Activity History and Settings
NAV_ITEMS = [
    ("Dashboard", ""),
    ("Processes", ""),
    ("Storage", ""),
    ("Battery", ""),
    ("Startup Apps", ""),
    ("Applications", ""),
    ("Recommendations", ""),
    ("Activity History", ""),
    ("Settings", ""),
]
