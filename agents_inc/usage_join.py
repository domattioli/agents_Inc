"""Spec 016 FR-003 (#36): read-only join from ledger nodes to usage.db rows.

Python 3.9 stdlib only. Never raises; any error returns None.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def usage_for(workspace, node_id, *, db_path=None):
    """Join ledger node to usage.db rows by time window.

    Returns dict with token sums and match type, or None if unknown.
    Never raises. Never creates files or modifies database.
    """
    try:
        if db_path is None:
            db_path = Path.home() / ".codex-bridge" / "usage.db"
        else:
            db_path = Path(db_path)

        # Read ledger
        ledger_path = Path(workspace) / ".workerbees" / "ledger.jsonl"
        if not ledger_path.exists():
            return None

        rows = []
        with ledger_path.open("r") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                    if row.get("id") == node_id:
                        rows.append(row)
                except (json.JSONDecodeError, ValueError):
                    continue

        if not rows:
            return None

        # Find dispatch row (first with status "dispatched")
        dispatch_row = None
        for row in rows:
            if row.get("status") == "dispatched":
                dispatch_row = row
                break

        if not dispatch_row:
            return None

        # Check source
        if dispatch_row.get("source") == "host-hook":
            return None

        # Check provider
        provider = dispatch_row.get("provider")
        if provider == "claude":
            return None

        # Get model
        model = dispatch_row.get("model")
        if not model or not provider:
            return None

        # Find window end (max timestamp of later rows)
        dispatch_ts = dispatch_row.get("timestamp")
        if not dispatch_ts:
            return None

        dispatch_dt = _try_parse(dispatch_ts)
        if dispatch_dt is None:
            return None
        end_dt = _latest_after(rows, dispatch_dt)
        if end_dt is None:
            return None

        # Check for overlapping nodes with same provider/model
        all_rows = []
        with ledger_path.open("r") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                    all_rows.append(row)
                except (json.JSONDecodeError, ValueError):
                    continue

        # Group by node id
        nodes = {}
        for row in all_rows:
            node = row.get("id")
            if node not in nodes:
                nodes[node] = []
            nodes[node].append(row)

        # Check for overlaps
        for other_id, other_rows in nodes.items():
            if other_id == node_id:
                continue

            other_dispatch = None
            for row in other_rows:
                if row.get("status") == "dispatched":
                    other_dispatch = row
                    break

            if not other_dispatch:
                continue

            if other_dispatch.get("provider") != provider or other_dispatch.get("model") != model:
                continue

            other_dispatch_ts = other_dispatch.get("timestamp")
            if not other_dispatch_ts:
                continue

            other_dispatch_dt = _try_parse(other_dispatch_ts)
            if other_dispatch_dt is None:
                continue
            other_end_dt = _latest_after(other_rows, other_dispatch_dt)
            if other_end_dt is None:
                continue

            # Check overlap: windows overlap if start1 <= end2 and end1 >= start2
            if (other_dispatch_dt <= end_dt and other_end_dt >= dispatch_dt):
                return None

        # Connect to database
        if not db_path.exists():
            return None

        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            # Query all rows for backend (no timestamp filter in SQL)
            query = """
            SELECT ts, model, input_tokens, output_tokens, cache_read, cache_write
            FROM usage
            WHERE backend = ?
            """

            cursor = conn.execute(query, (provider,))
            all_rows = cursor.fetchall()

            # Filter by timestamp (datetime comparison) and model
            filtered = []
            for usage_row in all_rows:
                # Parse timestamp in Python (replace Z with +00:00)
                ts_str = usage_row["ts"]
                try:
                    usage_dt = parse_timestamp(ts_str)
                except (ValueError, AttributeError, TypeError):
                    continue  # Skip unparseable rows

                # Check timestamp in window
                if not (dispatch_dt <= usage_dt <= end_dt):
                    continue

                # Filter by model: exact match or model ends with "-<node_model>"
                usage_model = usage_row["model"] if usage_row["model"] else ""
                if usage_model == model or (usage_model and usage_model.endswith("-" + model)):
                    filtered.append(usage_row)

            if not filtered:
                return None

            # Sum tokens (NULL as 0 only inside sum, per spec)
            input_sum = sum((row["input_tokens"] or 0) for row in filtered)
            output_sum = sum((row["output_tokens"] or 0) for row in filtered)
            cache_read_sum = sum((row["cache_read"] or 0) for row in filtered)
            cache_write_sum = sum((row["cache_write"] or 0) for row in filtered)

            return {
                "input_tokens": input_sum,
                "output_tokens": output_sum,
                "cache_read": cache_read_sum,
                "cache_write": cache_write_sum,
                "rows": len(filtered),
                "match": "time-window"
            }

        finally:
            if conn:
                conn.close()

    except Exception:
        return None


def parse_timestamp(ts_str):
    """Parse a ledger (Z) or usage.db (ISO) timestamp to a timezone-aware datetime.

    A timestamp without an offset is read as UTC.
    """
    if ts_str.endswith("Z"):
        # Ledger format: replace trailing Z with +00:00 for fromisoformat
        ts_str = ts_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _try_parse(ts_str):
    """parse_timestamp, or None when the value is missing or unparseable."""
    try:
        return parse_timestamp(ts_str)
    except (ValueError, AttributeError, TypeError):
        return None


def _latest_after(rows, start_dt):
    """Latest parsed row timestamp strictly after start_dt, or None."""
    latest = None
    for r in rows:
        dt = _try_parse(r.get("timestamp"))
        if dt is not None and dt > start_dt and (latest is None or dt > latest):
            latest = dt
    return latest
