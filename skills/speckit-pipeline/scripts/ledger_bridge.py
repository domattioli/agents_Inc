#!/usr/bin/env python3
"""Record speckit-pipeline phase dispatches into this repo's real dispatch
ledger (workerbees.ledger), so pipeline runs get the same lineage/cost-rollup/
lint visibility as any other governed dispatch -- and so each phase's
deliverable gets a sha256 recorded the way specs/006-bindle-sibling-
integration's capture points (C1/C2/C3) expect, ready for Bindle to pick up
later without any pipeline-side change when that lands (D35).

Record-only: this does NOT execute the phase. The orchestrating session
still dispatches via the Agent tool exactly as before; this script is called
immediately before (dispatch) and after (return) that call to log it.
Never raises into the pipeline (matches ledger.py's own FR-008 fail-open
posture) -- a ledger write failure must never block or fail a pipeline run.

Usage:
  ledger_bridge.py dispatch --run-id R --node-id N --model MODEL --rung RUNG
      --task TASK --provider claude|codex [--parent-id P] [--edge-type E]
      [--gate-reason G] [--artifact-file PATH]
  ledger_bridge.py return --node-id N --status STATUS --seconds S
      [--subscription-calls C] [--artifact-file PATH]
  ledger_bridge.py new-run   # prints a fresh uuid4 to use as --run-id/--node-id

Prints the node_id (dispatch) or "ok"/"error" (return) to stdout. Exit 0
always (fail-open) except on argument-parse errors (exit 2, argparse default).

RUNG-TO-SCHEMA-TIER MAPPING (found and fixed 2026-09-07, see D35 report):
the ledger's SQLite schema (docs/governance/SCHEMA-3NF.md) hardcodes
`tier CHECK (tier IN ('cheap','mid','frontier'))` -- the pre-D27 3-tier
vocabulary, not the D27 4-rung names. Passing a rung name straight into
`tier` raises sqlite3.IntegrityError inside ledger._dual_write_dispatch,
silently swallowed by its own bare `except IntegrityError: pass` -- the
node never persists to SQLite (JSONL still writes fine), while
record_dispatch still reports success. Verified by direct repro before
this script existed; not touching the shared schema (used by the whole
repo's governance slice, higher blast radius than this task warrants).
Fix: map rung -> schema tier for the actual `tier=` column (this also
correctly reuses existing frontier-tier lint/gate-reason semantics --
gateway.py:192, ledger.py:526 both key off tier=="frontier"), and fold
the precise rung name into `task` so no information is lost:
"""
from __future__ import annotations
import argparse
import hashlib
import sys
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from workerbees import ledger  # noqa: E402

_RUNG_TO_SCHEMA_TIER = {
    "executive": "frontier",
    "orchestrator": "frontier",
    "supervisor": "frontier",  # D34 synonym for orchestrator
    "workhorse": "mid",
    "grunt": "cheap",
}


def _schema_tier(rung: str) -> str:
    key = rung.strip().lower()
    if key not in _RUNG_TO_SCHEMA_TIER:
        raise ValueError(
            f"unknown rung {rung!r}; expected one of "
            f"{sorted(set(_RUNG_TO_SCHEMA_TIER) - {'supervisor'})} (or its D34 synonym 'Supervisor')"
        )
    return _RUNG_TO_SCHEMA_TIER[key]


def _sha256_file(path: str | None) -> tuple[str | None, int]:
    if not path:
        return None, 0
    p = Path(path)
    if not p.exists():
        print(f"WARN: artifact file not found, recording without hash: {path}", file=sys.stderr)
        return None, 0
    data = p.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def _workspace(args: argparse.Namespace) -> Path:
    return Path(args.repo_root) if getattr(args, "repo_root", None) else _REPO_ROOT


def cmd_dispatch(args: argparse.Namespace) -> int:
    try:
        schema_tier = _schema_tier(args.rung)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 0  # fail-open: never block the pipeline over a bad rung name
    artifact_hash, artifact_size = _sha256_file(args.artifact_file)
    ok = ledger.record_dispatch(
        _workspace(args),
        node_id=args.node_id,
        run_id=args.run_id,
        model=args.model,
        tier=schema_tier,
        task=f"{args.task}:{args.rung}",
        provider=args.provider,
        parent_id=args.parent_id,
        edge_type=args.edge_type,
        gate_reason=args.gate_reason,
        artifact_hash=artifact_hash,
        artifact_size=artifact_size,
    )
    print(args.node_id if ok else f"WARN: ledger write failed (non-fatal), node_id={args.node_id}")
    return 0


def cmd_return(args: argparse.Namespace) -> int:
    artifact_hash, artifact_size = _sha256_file(args.artifact_file)
    if artifact_hash:
        # record_return has no artifact_hash param -- a second dispatch-shaped
        # row with the same node_id would violate idempotency-on-node-id, so
        # print it for the caller to surface instead of writing it silently.
        print(f"NOTE: artifact sha256={artifact_hash} size={artifact_size} "
              f"(not written by 'return' -- ledger.record_return has no artifact param; "
              f"pass --artifact-file on the 'dispatch' call instead)", file=sys.stderr)
    ok = ledger.record_return(
        _workspace(args),
        node_id=args.node_id,
        status=args.status,
        seconds=args.seconds,
        subscription_calls=args.subscription_calls,
    )
    print("ok" if ok else "WARN: ledger write failed (non-fatal)")
    return 0


def cmd_new_run(_args: argparse.Namespace) -> int:
    print(str(uuid.uuid4()))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dispatch")
    d.add_argument("--repo-root", default=None, help="ledger workspace (default: this repo)")
    d.add_argument("--run-id", required=True)
    d.add_argument("--node-id", required=True)
    d.add_argument("--model", required=True)
    d.add_argument("--rung", required=True, help="Executive|Orchestrator|Supervisor|Workhorse|Grunt")
    d.add_argument("--task", required=True, help="e.g. speckit-plan")
    d.add_argument("--provider", required=True, choices=["claude", "codex"])
    d.add_argument("--parent-id", default=None)
    d.add_argument("--edge-type", default="dispatches")
    d.add_argument("--gate-reason", default=None)
    d.add_argument("--artifact-file", default=None)
    d.set_defaults(func=cmd_dispatch)

    r = sub.add_parser("return")
    r.add_argument("--repo-root", default=None, help="ledger workspace (default: this repo)")
    r.add_argument("--node-id", required=True)
    r.add_argument("--status", required=True, choices=["verified", "needs-review", "red", "denied"])
    r.add_argument("--seconds", type=float, required=True)
    r.add_argument("--subscription-calls", type=int, default=1)
    r.add_argument("--artifact-file", default=None)
    r.set_defaults(func=cmd_return)

    nr = sub.add_parser("new-run")
    nr.set_defaults(func=cmd_new_run)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
