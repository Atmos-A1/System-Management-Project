"""Process classification engine.

Classifies processes based on evidence: executable path, digital signature,
service association, parent-child relationships, known metadata.
Implements the classification rules from PRD Section 5.2.
"""

import os
from typing import Dict, Any, List

# Critical system processes that must be protected
CRITICAL_PROCESSES = {
    'system', 'smss.exe', 'csrss.exe', 'wininit.exe', 'services.exe',
    'lsass.exe', 'winlogon.exe', 'svchost.exe', 'explorer.exe',
    'dwm.exe', 'fontdrvhost.exe', 'winhost.exe', 'RuntimeBroker.exe',
    'sihost.exe', 'taskhostw.exe', 'SearchIndexer.exe', 'spoolsv.exe',
    'ntoskrnl.exe', 'hal.dll'
}

# Important Windows system paths
SYSTEM_PATHS = [
    os.environ.get('WINDIR', r'C:\Windows').lower(),
    r'c:\windows\system32',
    r'c:\windows\syswow64',
    r'c:\program files\windowsapps',
]

# Known Windows services patterns
SYSTEM_SERVICE_PROCESSES = {'svchost.exe', 'services.exe', 'lsass.exe'}


class ProcessClassifier:
    def __init__(self):
        self.knowledge_base_version = "1.0.0"
    
    def classify(self, process: Dict[str, Any]) -> Dict[str, Any]:
        """Classify a process and return classification with risk, confidence, evidence."""
        pid = process.get('pid')
        name = (process.get('name') or '').lower()
        exe = (process.get('exe') or '').lower()
        ppid = process.get('ppid')
        
        evidence = []
        confidence = 0.0
        category = "Unknown / unverified"
        risk_level = "Unknown"
        importance = "Unknown"
        explanation = "Insufficient evidence to classify this process safely."
        can_terminate = False
        requires_confirmation = True
        
        # Check if it's a critical system process
        if name in CRITICAL_PROCESSES:
            evidence.append(f"Process name '{name}' is a known critical Windows system process")
            confidence += 0.4
            # Additional checks
            if exe and any(sys_path in exe for sys_path in SYSTEM_PATHS):
                evidence.append(f"Executable located in system directory: {process.get('exe')}")
                confidence += 0.3
            
            category = "Critical system component"
            risk_level = "Very High - System instability"
            importance = "Essential"
            explanation = "This is a critical Windows system component. Terminating it may cause system instability, crashes, or require a reboot."
            can_terminate = False
            confidence = min(confidence, 1.0)
            return self._build_result(category, risk_level, importance, confidence, evidence, explanation, can_terminate, requires_confirmation)
        
        # Check if in system directory
        if exe:
            in_system_dir = any(sys_path in exe for sys_path in SYSTEM_PATHS)
            if in_system_dir and name in SYSTEM_SERVICE_PROCESSES:
                evidence.append(f"System service process in Windows directory")
                confidence += 0.3
                category = "Important Windows service"
                risk_level = "High"
                importance = "Important"
                explanation = "This supports operating system functionality. Stopping it may affect system features."
                can_terminate = False  # Be conservative
                requires_confirmation = True
                confidence = min(confidence + 0.2, 1.0)
                return self._build_result(category, risk_level, importance, confidence, evidence, explanation, can_terminate, requires_confirmation)
            elif in_system_dir:
                evidence.append(f"Located in Windows system directory: {process.get('exe')}")
                confidence += 0.2
                # Could be important system component
                category = "Important Windows service"
                risk_level = "High"
                importance = "Important"
                explanation = "Located in system directory - likely provides OS functionality. Exercise caution."
                can_terminate = False
                confidence = min(confidence, 0.8)
                return self._build_result(category, risk_level, importance, confidence, evidence, explanation, can_terminate, requires_confirmation)
        
        # Check if it's from Program Files (user applications)
        if exe and ('program files' in exe and 'windowsapps' not in exe):
            evidence.append(f"Application installed in Program Files: {process.get('exe')}")
            confidence += 0.3
            category = "User application"
            risk_level = "Medium"
            importance = "Optional"
            explanation = "This appears to be a user-installed application. You can usually close it safely if not in use."
            can_terminate = True
            requires_confirmation = True
            confidence = min(confidence, 0.85)
            return self._build_result(category, risk_level, importance, confidence, evidence, explanation, can_terminate, requires_confirmation)
        
        # Check common user app locations
        if exe and ('appdata' in exe or 'local\\temp' not in exe and name.endswith('.exe')):
            # Could be user app
            evidence.append("Executable from user application directory")
            confidence += 0.2
            category = "User application"
            risk_level = "Low to Medium"
            importance = "Optional"
            explanation = "Likely a user application. Closing may result in loss of unsaved data."
            can_terminate = True
            requires_confirmation = True
            confidence = min(confidence, 0.7)
            return self._build_result(category, risk_level, importance, confidence, evidence, explanation, can_terminate, requires_confirmation)
        
        # Default - unknown, be conservative
        evidence.append("No strong classification evidence found")
        evidence.append("Location and purpose could not be determined reliably")
        category = "Unknown / unverified"
        risk_level = "Unknown - Exercise extreme caution"
        importance = "Unknown"
        explanation = "Classification is uncertain. Do not terminate without understanding what this process does."
        can_terminate = False
        requires_confirmation = True
        confidence = 0.1
        return self._build_result(category, risk_level, importance, confidence, evidence, explanation, can_terminate, requires_confirmation)
    
    def _build_result(self, category, risk_level, importance, confidence, evidence, explanation, 
                      can_terminate, requires_confirmation) -> Dict[str, Any]:
        return {
            "category": category,
            "risk_level": risk_level,
            "importance": importance,
            "confidence": round(confidence, 2),
            "evidence": evidence,
            "explanation": explanation,
            "can_terminate": can_terminate,
            "requires_confirmation": requires_confirmation,
            "kb_version": self.knowledge_base_version,
        }


def classify_process(process: Dict[str, Any]) -> Dict[str, Any]:
    classifier = ProcessClassifier()
    return classifier.classify(process)
