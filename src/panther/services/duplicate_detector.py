"""Duplicate file detector.

Uses file size as preliminary filter, then cryptographic hash (SHA256)
to identify exact duplicates.
"""

import hashlib
import os
from typing import List, Dict, Any
from collections import defaultdict


class DuplicateDetector:
    def __init__(self, hash_algorithm: str = 'sha256'):
        self.hash_algorithm = hash_algorithm
    
    def calculate_hash(self, file_path: str, chunk_size: int = 8192) -> str:
        """Calculate hash of file contents."""
        hash_obj = hashlib.new(self.hash_algorithm)
        try:
            with open(file_path, 'rb') as f:
                while chunk := f.read(chunk_size):
                    hash_obj.update(chunk)
            return hash_obj.hexdigest()
        except (PermissionError, OSError):
            return None
    
    def find_duplicates(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Find duplicate files by content hash."""
        # Group by size first for efficiency
        size_groups = defaultdict(list)
        seen_ids = set()
        for f in files:
            if f.get('size', 0) <= 0:  # Skip empty files
                continue
            # Hardlinks share one on-disk file: they are not extra copies and
            # deleting one frees no space, so keep only the first path seen.
            file_id = (f.get('device'), f.get('inode'))
            if file_id[1]:
                if file_id in seen_ids:
                    continue
                seen_ids.add(file_id)
            size_groups[f['size']].append(f)
        
        duplicates = []
        # Only check groups with potential duplicates (2+ files same size)
        for size, file_list in size_groups.items():
            if len(file_list) < 2:
                continue
            
            # Hash files in this size group
            hash_groups = defaultdict(list)
            for f in file_list:
                file_hash = self.calculate_hash(f['path'])
                if file_hash:
                    f['hash'] = file_hash
                    hash_groups[file_hash].append(f)
            
            # Groups with 2+ files have duplicates
            for file_hash, dup_list in hash_groups.items():
                if len(dup_list) >= 2:
                    total_size = size * len(dup_list)
                    potential_savings = size * (len(dup_list) - 1)
                    duplicates.append({
                        'hash': file_hash,
                        'size': size,
                        'count': len(dup_list),
                        'files': dup_list,
                        'total_size': total_size,
                        'potential_savings': potential_savings,
                    })
        
        # Sort by potential savings
        duplicates.sort(key=lambda x: x['potential_savings'], reverse=True)
        return duplicates


duplicate_detector = DuplicateDetector()
