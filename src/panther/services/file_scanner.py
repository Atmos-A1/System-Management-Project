"""File scanner service.

Scans directories to collect file metadata for analysis.
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


class FileScanner:
    def __init__(self):
        self.scanning = False
        self.cancelled = False
    
    def scan_directory(self, root_path: str, max_depth: int = 10, 
                      include_hidden: bool = False) -> List[Dict[str, Any]]:
        """Scan directory and return file information."""
        files = []
        self.scanning = True
        self.cancelled = False
        
        try:
            root = Path(root_path)
            if not root.exists():
                return files
            
            for dirpath, dirnames, filenames in os.walk(root, topdown=True):
                if self.cancelled:
                    break
                
                # Skip hidden directories if requested
                if not include_hidden:
                    dirnames[:] = [d for d in dirnames if not d.startswith('.')]
                
                for filename in filenames:
                    if self.cancelled:
                        break
                    if not include_hidden and filename.startswith('.'):
                        continue
                    
                    try:
                        full_path = os.path.join(dirpath, filename)
                        stat = os.stat(full_path)
                        
                        files.append({
                            'name': filename,
                            'path': full_path,
                            'directory': dirpath,
                            'size': stat.st_size,
                            'extension': Path(filename).suffix.lower(),
                            'created': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                            'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                            'accessed': datetime.fromtimestamp(stat.st_atime).strftime('%Y-%m-%d %H:%M:%S') if hasattr(stat, 'st_atime') else None,
                            'is_file': True,
                        })
                    except (PermissionError, OSError):
                        continue
        finally:
            self.scanning = False
        
        return files
    
    def get_largest_files(self, files: List[Dict[str, Any]], limit: int = 100) -> List[Dict[str, Any]]:
        """Get largest files sorted by size."""
        sorted_files = sorted(files, key=lambda x: x['size'], reverse=True)
        return sorted_files[:limit]
    
    def cancel(self):
        self.cancelled = True


file_scanner = FileScanner()
