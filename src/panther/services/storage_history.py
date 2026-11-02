"""Summary-only persistence and retrieval for Storage scans.

Scan summaries reuse the existing ``history`` table. Full file lists and
duplicate groups are never stored here.
"""

import datetime
import json
import math
from typing import Any, Dict, List

from . import history

EVENT_CATEGORY = "storage_scan"
_MAX_FETCH = 1000
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 500


def _as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def _as_float(value) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _error_count(errors) -> int:
    return len(errors) if isinstance(errors, (list, tuple)) else 0


def record_scan(payload: Dict[str, Any], status: str) -> bool:
    """Record one scan summary, returning ``False`` if persistence fails."""
    payload = payload if isinstance(payload, dict) else {}
    errors = payload.get("errors") or []
    bytes_processed = payload.get(
        "bytes_scanned", payload.get("bytes_hashed", 0)
    )

    try:
        summary = {
            "status": str(status or "unknown"),
            "kind": str(payload.get("kind") or "unknown"),
            "root": str(payload.get("root") or ""),
            "files_scanned": _as_int(payload.get("files_scanned")),
            "directories_scanned": _as_int(
                payload.get("directories_scanned")
            ),
            "bytes_processed": _as_int(bytes_processed),
            "elapsed_seconds": _as_float(
                payload.get("elapsed_seconds")
            ),
            "skipped_count": _as_int(
                payload.get("skipped_count", _error_count(errors))
            ),
        }
        if payload.get("error"):
            summary["error"] = str(payload["error"])[:500]

        history.record_event(
            EVENT_CATEGORY, json.dumps(summary, default=str)
        )
        return True
    except Exception:
        # History is best-effort and must never affect scan results.
        return False


def _parse_detail(detail) -> Dict[str, Any]:
    try:
        data = json.loads(detail)
    except (TypeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}

    return {
        "status": str(data.get("status") or "unknown"),
        "kind": str(data.get("kind") or "unknown"),
        "root": str(data.get("root") or ""),
        "files_scanned": _as_int(data.get("files_scanned")),
        "directories_scanned": _as_int(
            data.get("directories_scanned")
        ),
        "bytes_processed": _as_int(data.get("bytes_processed")),
        "elapsed_seconds": _as_float(data.get("elapsed_seconds")),
        "skipped_count": _as_int(data.get("skipped_count")),
        "error": str(data.get("error") or ""),
    }


def get_scan_history(limit: int = 100) -> List[Dict[str, Any]]:
    """Return up to *limit* storage scan summaries, newest first."""
    try:
        limit = max(1, int(limit or 1))
    except (TypeError, ValueError):
        limit = 100

    # The history service only supports a row limit. Fetch a bounded window so
    # unrelated events do not starve the Storage view.
    fetch_limit = min(max(limit * 5, limit), _MAX_FETCH)
    try:
        rows = history.get_recent(fetch_limit)
    except Exception:
        return []

    records = []
    for row in rows or []:
        try:
            row_id, timestamp, category, detail = row
        except (TypeError, ValueError):
            continue
        if category != EVENT_CATEGORY:
            continue
        record = _parse_detail(detail)
        record["id"] = row_id
        record["timestamp"] = str(timestamp or "")
        records.append(record)
        if len(records) >= limit:
            break
    return records


def _normalise_date(value, label: str):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"{label} must be a valid date in YYYY-MM-DD format."
        ) from exc
    return parsed


def _like_pattern(value: str) -> str:
    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


def _coerce_page(value, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(1, number)


def get_scan_history_page(
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    kind=None,
    status=None,
    start_date=None,
    end_date=None,
    search=None,
    max_id=None,
) -> Dict[str, Any]:
    """Return one filtered page of summary-only scan history.

    Filtering and pagination happen in SQLite. ``max_id`` anchors navigation to
    the newest record visible when the first page was loaded, so events appended
    during normal navigation cannot shift or duplicate rows.
    """
    page = _coerce_page(page, 1)
    try:
        page_size = int(page_size)
    except (TypeError, ValueError, OverflowError):
        page_size = DEFAULT_PAGE_SIZE
    page_size = min(MAX_PAGE_SIZE, max(1, page_size))

    start = _normalise_date(start_date, "Start date")
    end = _normalise_date(end_date, "End date")
    if start is not None and end is not None and start > end:
        raise ValueError("Start date must be on or before end date.")

    clauses = ["category = ?"]
    params: List[Any] = [EVENT_CATEGORY]

    kind_value = str(kind or "").strip().lower()
    if kind_value:
        clauses.append(
            "json_valid(detail) AND "
            "json_extract(detail, '$.kind') = ?"
        )
        params.append(kind_value)

    status_value = str(status or "").strip().lower()
    if status_value:
        clauses.append(
            "json_valid(detail) AND "
            "json_extract(detail, '$.status') = ?"
        )
        params.append(status_value)

    if start is not None:
        clauses.append("ts >= ?")
        params.append(f"{start.isoformat()}T00:00:00")
    if end is not None:
        clauses.append("ts <= ?")
        params.append(f"{end.isoformat()}T23:59:59.999999")

    search_value = str(search or "").strip()
    if search_value:
        pattern = _like_pattern(search_value)
        clauses.append(
            "(detail LIKE ? ESCAPE '\\' OR category LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern, pattern])

    if max_id is None:
        anchor_rows = history.db.fetchall(
            f"SELECT COALESCE(MAX(id), 0) AS max_id "
            f"FROM {history.TABLE_NAME} WHERE category = ?",
            (EVENT_CATEGORY,),
        )
        anchor = int(anchor_rows[0]["max_id"]) if anchor_rows else 0
    else:
        try:
            anchor = max(0, int(max_id))
        except (TypeError, ValueError, OverflowError):
            anchor = 0
    clauses.append("id <= ?")
    params.append(anchor)

    where_sql = " AND ".join(clauses)
    count_rows = history.db.fetchall(
        f"SELECT COUNT(*) AS total FROM {history.TABLE_NAME} "
        f"WHERE {where_sql}",
        tuple(params),
    )
    try:
        total = int(count_rows[0]["total"]) if count_rows else 0
    except (TypeError, ValueError, OverflowError):
        total = 0

    page_count = math.ceil(total / page_size) if total else 0
    if page_count:
        page = min(page, page_count)
    else:
        page = 1
    offset = (page - 1) * page_size

    rows = history.db.fetchall(
        f"SELECT id, ts, category, detail FROM {history.TABLE_NAME} "
        f"WHERE {where_sql} ORDER BY ts DESC, id DESC "
        f"LIMIT ? OFFSET ?",
        tuple(params) + (page_size, offset),
    )

    records = []
    for row in rows or []:
        try:
            record = _parse_detail(row["detail"])
            record["id"] = row["id"]
            record["timestamp"] = str(row["ts"] or "")
        except (TypeError, ValueError, KeyError, IndexError):
            continue
        records.append(record)

    start_index = offset + 1 if total else 0
    end_index = offset + len(records) if total else 0
    return {
        "records": records,
        "total": total,
        "page": page,
        "page_size": page_size,
        "page_count": page_count,
        "has_previous": bool(total and page > 1),
        "has_next": bool(total and page < page_count),
        "start_index": start_index,
        "end_index": end_index,
        "max_id": anchor,
        "filters": {
            "kind": kind_value or None,
            "status": status_value or None,
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
            "search": search_value or None,
        },
    }
