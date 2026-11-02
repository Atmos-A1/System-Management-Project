"""Recommendations screen - smart suggestions.

Displays evidence-based recommendations with impact, risk, and actions.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, 
    QHBoxLayout, QPushButton
)
from PySide6.QtCore import Qt, QTimer

from ..config import config
from ..services.recommendation_engine import get_recommendations
from ..services.system_monitor import (
    get_cpu_percent,
    get_ram_usage,
    get_disk_usage,
    get_battery_info,
)


class RecommendationCard(QFrame):
    def __init__(self, rec, navigate_callback=None):
        super().__init__()
        self.rec = rec
        self.navigate_callback = navigate_callback
        self.setObjectName("recCard")
        impact = rec.get('impact', 'Medium')
        accent = "#2563eb"
        if impact == 'Critical':
            accent = "#dc2626"
        elif impact == 'High':
            accent = "#f59e0b"
        elif impact == 'Low':
            accent = "#22c55e"
        
        self.setStyleSheet(f"""
            QFrame#recCard {{
                background-color: #ffffff;
                border-radius: 10px;
                border: 1px solid #e5e7eb;
                border-left: 4px solid {accent};
            }}
            QFrame#recCard:hover {{
                border: 1px solid #93c5fd;
                border-left: 4px solid {accent};
            }}
        """)
        self.setCursor(Qt.PointingHandCursor)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        
        # Header
        header_layout = QHBoxLayout()
        issue_label = QLabel(rec.get('issue', ''))
        issue_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #111827;")
        issue_label.setWordWrap(True)
        header_layout.addWidget(issue_label)
        header_layout.addStretch()
        
        impact_label = QLabel(f"Impact: {impact}")
        if impact == 'Critical':
            impact_label.setStyleSheet("color: #dc2626; font-weight: 600;")
        elif impact == 'High':
            impact_label.setStyleSheet("color: #d97706; font-weight: 600;")
        elif impact == 'Low':
            impact_label.setStyleSheet("color: #16a34a; font-weight: 600;")
        else:
            impact_label.setStyleSheet("color: #6b7280; font-weight: 600;")
        header_layout.addWidget(impact_label)
        layout.addLayout(header_layout)
        
        # Evidence
        evidence = QLabel(f"<b>Evidence:</b> {rec.get('evidence', '')}")
        evidence.setWordWrap(True)
        evidence.setStyleSheet("color: #374151;")
        layout.addWidget(evidence)
        
        # Why it matters
        if rec.get('why'):
            why = QLabel(f"<b>Why it matters:</b> {rec.get('why', '')}")
            why.setWordWrap(True)
            why.setStyleSheet("color: #374151;")
            layout.addWidget(why)
        
        # Benefit
        benefit = QLabel(f"<b>Benefit:</b> {rec.get('benefit', '')}")
        benefit.setWordWrap(True)
        benefit.setStyleSheet("color: #16a34a;")
        layout.addWidget(benefit)
        
        # Risk
        risk = QLabel(f"<b>Risk:</b> {rec.get('risk', '')}")
        risk.setWordWrap(True)
        risk.setStyleSheet("color: #d97706;")
        layout.addWidget(risk)
        
        # Action
        action_label = QLabel(f"<b>Recommended Action:</b> {rec.get('action', '')}")
        action_label.setWordWrap(True)
        action_label.setStyleSheet("color: #2563eb;")
        layout.addWidget(action_label)
        
        # Footer
        footer = QHBoxLayout()
        if rec.get('confidence'):
            conf = QLabel(f"Confidence: {rec['confidence']:.0%}  |  Safety: {rec.get('safety', 'N/A')}  |  Category: {rec.get('category', 'General')}")
            conf.setStyleSheet("color: #6b7280; font-size: 11px;")
            footer.addWidget(conf)
        footer.addStretch()
        go_btn = QPushButton("Go to fix →")
        go_btn.setStyleSheet("padding: 6px 10px; border-radius: 6px; background-color: #f3f4f6; color: #111827; border: 1px solid #d1d5db;")
        go_btn.clicked.connect(self._go_to_fix)
        footer.addWidget(go_btn)
        layout.addLayout(footer)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._go_to_fix()
        super().mousePressEvent(event)
    
    def _go_to_fix(self):
        if self.navigate_callback:
            self.navigate_callback(self.rec)


class RecommendationsScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("recommendationsScreen")
        self.setStyleSheet("""
            QWidget {
                background-color: #f7f9fc;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        header = QLabel("Smart Recommendations")
        header.setStyleSheet("font-size: 24px; font-weight: 700; color: #111827;")
        layout.addWidget(header)
        
        subtitle = QLabel("Evidence-based suggestions to optimize your system safely")
        subtitle.setStyleSheet("font-size: 12px; color: #6b7280;")
        layout.addWidget(subtitle)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background-color: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(12)
        self.content_layout.setContentsMargins(0, 0, 4, 0)
        self.content_layout.setAlignment(Qt.AlignTop)
        
        scroll.setWidget(self.content_widget)
        layout.addWidget(scroll)
        
        self.timer = QTimer(self)
        self.timer.setInterval(config.refresh_interval_seconds * 1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def _gather_metrics(self):
        try:
            cpu = get_cpu_percent()
            ram = get_ram_usage()["percent"]
            disk = get_disk_usage()["percent"]
            batt_info = get_battery_info()
            batt = batt_info.get("percent") if batt_info else None
            return {"cpu_percent": cpu, "ram_percent": ram, "disk_percent": disk, "battery_percent": batt}
        except Exception:
            return {"cpu_percent": 0, "ram_percent": 0, "disk_percent": 0, "battery_percent": None}

    def navigate_to_fix(self, rec):
        category = (rec.get('category') or '').lower()
        issue = (rec.get('issue') or '').lower()
        # Try to find parent window/main window
        parent = self.window()
        if hasattr(parent, 'sidebar') and hasattr(parent, 'stack'):
            # Map by index based on NAV_ITEMS order
            from .navigation import NAV_ITEMS
            target = None
            if 'process' in category or 'cpu' in issue or 'memory' in issue or 'ram' in issue:
                target = "Processes"
            elif 'storage' in category or 'disk' in issue:
                target = "Storage"
            elif 'power' in category or 'battery' in issue:
                target = "Battery"
            elif 'startup' in issue:
                target = "Startup Apps"
            # Find index
            for i, (name, _icon) in enumerate(NAV_ITEMS):
                if name == target:
                    parent.sidebar.setCurrentRow(i)
                    parent.stack.setCurrentIndex(i)
                    return
        # Fallback: try common indices
        if 'process' in category or 'cpu' in issue:
            try:
                parent.sidebar.setCurrentRow(1)  # Processes
            except Exception:
                pass
        elif 'storage' in category or 'disk' in issue:
            try:
                parent.sidebar.setCurrentRow(2)  # Storage
            except Exception:
                pass
        elif 'power' in category or 'battery' in issue:
            try:
                parent.sidebar.setCurrentRow(3)  # Battery
            except Exception:
                pass

    def refresh(self):
        for i in reversed(range(self.content_layout.count())):
            item = self.content_layout.itemAt(i)
            if item.widget():
                item.widget().deleteLater()
        
        metrics = self._gather_metrics()
        recs = get_recommendations(metrics)
        
        if not recs:
            no_rec = QLabel("✓ Your system looks good! No recommendations at this time.")
            no_rec.setStyleSheet("font-size: 14px; color: #16a34a; padding: 24px; background-color: #ffffff; border-radius: 10px; border: 1px solid #e5e7eb;")
            no_rec.setAlignment(Qt.AlignCenter)
            self.content_layout.addWidget(no_rec)
        else:
            for rec in recs:
                card = RecommendationCard(rec, navigate_callback=self.navigate_to_fix)
                self.content_layout.addWidget(card)
        
        self.content_layout.addStretch()
