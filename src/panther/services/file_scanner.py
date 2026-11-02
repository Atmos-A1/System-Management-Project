"""File scanner service.

Scans directories to collect file metadata for analysis.
"""

import os
import stat as stat_module
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


def _is_link_like(path: str) -> bool:
    """True for symlinks and (on Windows) junctions, which must not be followed."""
    try:
        if os.path.islink(path):
            return True
        isjunction = getattr(os.path, "isjunction", None)
        return bool(isjunction and isjunction(path))
    except OSError:
        return True


class FileScanner:
    def __init__(self):
        self.scanning = False
        self.cancelled = False

    def scan_directory(self, root_path: str, max_depth: int = 10,
                      include_hidden: bool = False) -> List[Dict[str, Any]]:
        """Scan directory and return file information.

        ``max_depth`` is the number of directory levels below ``root_path`` that
        are descended into (0 = only files directly inside ``root_path``).
        Symbolic links and junctions are never followed or listed, so a link can
        not be mistaken for a second copy of a file or cause a scan loop.
        """
        files = []
        self.scanning = True
        self.cancelled = False

        try:
            root = Path(root_path)
            if not root.exists():
                return files
            root_str = os.fspath(root)
            root_depth = root_str.rstrip(os.sep).count(os.sep)

            for dirpath, dirnames, filenames in os.walk(root, topdown=True):
                if self.cancelled:
                    break

                depth = dirpath.rstrip(os.sep).count(os.sep) - root_depth
                # Prune: hidden dirs (optional), links/junctions, and anything past max_depth.
                dirnames[:] = [
                    d for d in dirnames
                    if (include_hidden or not d.startswith('.'))
                    and not _is_link_like(os.path.join(dirpath, d))
                ]
                if depth >= max_depth:
                    dirnames[:] = []

                for filename in filenames:
                    if self.cancelled:
                        break
                    if not include_hidden and filename.startswith('.'):
                        continue

                    try:
                        full_path = os.path.join(dirpath, filename)
                        st = os.lstat(full_path)
                        if stat_module.S_ISLNK(st.st_mode) or not stat_module.S_ISREG(st.st_mode):
                            continue

                        files.append({
                            'name': filename,
                            'path': full_path,
                            'directory': dirpath,
                            'size': st.st_size,
                            'extension': Path(filename).suffix.lower(),
                            'created': datetime.fromtimestamp(st.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                            'modified': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                            'accessed': datetime.fromtimestamp(st.st_atime).strftime('%Y-%m-%d %H:%M:%S'),
                            'device': st.st_dev,
                            'inode': st.st_ino,
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
