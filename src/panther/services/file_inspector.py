"""Combined read-only metadata and signature inspection for one entry."""

import os
from typing import Any, Dict, Optional

from .file_metadata import FileMetadataInspector
from .file_signature import FileSignatureInspector


def _not_applicable(metadata: Dict[str, Any]) -> Dict[str, Any]:
    entry_type = metadata.get("entry_type")
    if entry_type == "directory":
        reason = "Signatures are not applicable to directories."
    elif entry_type in ("link", "reparse"):
        reason = "Links and reparse points are not inspected."
    else:
        reason = "Only regular files have signatures."
    return {
        "ok": False,
        "path": metadata.get("path", ""),
        "name": metadata.get("name", ""),
        "status": "unsupported",
        "format": None,
        "format_label": None,
        "entry_type": entry_type,
        "extension": metadata.get("extension", ""),
        "extension_match": "unavailable",
        "bytes_read": 0,
        "error": reason,
        "error_kind": entry_type or "unsupported",
        "no_follow_supported": bool(getattr(os, "O_NOFOLLOW", 0)),
    }


class FileInspector:
    """Inspect one selected entry without following links or opening files."""

    def __init__(
        self,
        metadata_inspector: Optional[FileMetadataInspector] = None,
        signature_inspector: Optional[FileSignatureInspector] = None,
    ):
        self.metadata_inspector = (
            metadata_inspector or FileMetadataInspector()
        )
        self.signature_inspector = (
            signature_inspector or FileSignatureInspector()
        )

    def inspect(self, path: str, cancel_event=None) -> Dict[str, Any]:
        if cancel_event is not None and cancel_event.is_set():
            return {"cancelled": True, "metadata": {}, "signature": {}}

        metadata = self.metadata_inspector.inspect(path)

        if cancel_event is not None and cancel_event.is_set():
            return {"cancelled": True, "metadata": metadata, "signature": {}}

        if metadata.get("ok") and metadata.get("entry_type") == "file":
            signature = self.signature_inspector.inspect(path)
        else:
            signature = _not_applicable(metadata)

        return {
            "cancelled": False,
            "metadata": metadata,
            "signature": signature,
        }
