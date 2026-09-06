#!/usr/bin/env bash
set -u
repo="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo" || exit 1
WORKERBEES_STORE=both python3 - <<'PY'
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from workerbees import ledger
from workerbees.adapters.base import WorkerResult
from workerbees.pipeline import brief
from workerbees.schema import QUERIES

fixtures = [(Path("fixtures/tim/matter.md"), "tim", "lawyer"),
            (Path("fixtures/dom/design.md"), "dom", "scientist")]
failed = False
with tempfile.TemporaryDirectory(prefix="audit_parity_") as td:
    workspace = Path(td)
    def runner(_cmd, stdin):
        source_id = "tim" if "Source id: tim" in stdin else "dom"
        text = stdin.split("[p1] ", 1)[1].split("\n\n[p2]", 1)[0].strip()
        payload = {"claims": [{"text": text, "quote": text, "anchor": f"{source_id}#p1"}],
                   "draft": f"{text} (p1)."}
        return WorkerResult("returned", json.dumps(payload), "", 0)

    for source, source_id, mode in fixtures:
        result = brief(source, source_id, mode, workspace, available={"claude"},
                       review_enabled=False, runner=runner)
        if result.receipt.get("ledger_error"):
            print(f"FAIL fixture={source_id} ledger_error={result.receipt['ledger_error']}")
            failed = True

    os.environ["WORKERBEES_STORE"] = "jsonl"
    jsonl = ledger.load(workspace)
    json_rollup = ledger.rollup(jsonl)
    roots = [node for node in jsonl.nodes.values() if node.parent_id is None]
    db = workspace / ".workerbees" / "workerbees.db"
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        for root in roots:
            row = conn.execute(QUERIES["q5"], {
                "root_id": root.id, "family_id": f"synthetic-{root.run_id}"
            }).fetchone()
            expected = json_rollup[root.id]
            missing = sum(n.subscription_calls is None for n in jsonl.nodes.values()
                          if n.run_id == root.run_id)
            ok = (row["node_count"] == 1 and
                  row["subscription_calls"] == expected["calls"] and
                  row["missing_count"] == missing)
            print(("PASS" if ok else "FAIL") +
                  f" run={root.run_id} root={root.id}" +
                  f" jsonl_nodes=1 sqlite_nodes={row['node_count']}" +
                  f" jsonl_calls={expected['calls']} sqlite_calls={row['subscription_calls']}" +
                  f" jsonl_missing={missing} sqlite_missing={row['missing_count']}")
            failed |= not ok
raise SystemExit(1 if failed else 0)
PY
