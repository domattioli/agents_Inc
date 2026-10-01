"""Host-side ledger: rows for delegated calls made from the host session (spec 016 DD3, DD4).

`record_hook_dispatch` turns a PostToolUse payload (Agent, Task, or a DelegateAgent MCP call)
into one dispatch row in a JSONL ledger under the user-scope state dir, never under the
project's cwd and never in SQLite. `cli` provides `append` (record a verified return with
an explicit verdict) and `pending` (list nodes still marked dispatched).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agents_inc import ledger

_MODELS_PATH = Path(__file__).resolve().parent / "models.json"
_TASK_CAP = 80
_VERDICT_MSG = ("agents-inc ledger append: --verdict pass|fail is required; "
                "a delegate self-report is not a verdict")


def host_workspace(state) -> Path:
    """Workspace dir holding the host ledger: <state>/host-ledger."""
    return Path(state) / "host-ledger"


def _models() -> dict:
    try:
        with open(_MODELS_PATH) as f:
            data = json.load(f)
        models = data.get("models", {})
        return models if isinstance(models, dict) else {}
    except Exception:
        return {}


def _tier(provider: str, model: str) -> str:
    models = _models()
    entry = models.get(model)
    if isinstance(entry, dict) and entry.get("tier"):
        return entry["tier"]
    if provider == "codex":
        for mid, info in models.items():
            if (isinstance(info, dict) and info.get("provider") == "codex"
                    and mid.endswith("-" + model) and info.get("tier")):
                return info["tier"]
    return "unknown"


def dispatch_row(payload) -> dict | None:
    """Build a Node-shaped dispatch row from a hook payload, or None when not a delegated call."""
    if not isinstance(payload, dict):
        return None
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    tool_use_id = payload.get("tool_use_id")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return None
    if not isinstance(tool_use_id, str) or not tool_use_id:
        return None

    if tool_name in ("Agent", "Task"):
        provider = "claude"
        model = tool_input.get("model") or "unknown"
        task = tool_input.get("description")
    elif tool_name.endswith("__DelegateAgent"):
        provider = "codex"
        model = tool_input.get("model") or "luna"
        prompt = tool_input.get("prompt")
        lines = prompt.splitlines() if isinstance(prompt, str) else []
        task = lines[0][:_TASK_CAP] if lines else None
    else:
        return None
    if not isinstance(model, str):
        model = "unknown"
    if task is not None and not isinstance(task, str):
        task = None

    session = payload.get("session_id")
    cwd = payload.get("cwd")
    return {
        "id": tool_use_id,
        "run_id": session if isinstance(session, str) and session else "unknown",
        "model": model,
        "tier": _tier(provider, model),
        "task": task,
        "provider": provider,
        "parent_id": None,
        "edge_type": None,
        "status": "dispatched",
        "seconds": None,
        "subscription_calls": None,
        "gate_reason": None,
        "artifact_hash": None,
        "effort": None,
        "input_tokens": None,
        "output_tokens": None,
        "cache_read": None,
        "cache_write": None,
        "files_created": None,
        "verdict": None,
        "cwd": cwd if isinstance(cwd, str) else None,
        "source": "host-hook",
        "timestamp": ledger._now_iso(),
    }


def record_hook_dispatch(state, payload) -> bool:
    """Append one dispatch row for a delegated-call payload. Never raises; JSONL only."""
    try:
        row = dispatch_row(payload)
        if row is None:
            return False
        d = host_workspace(state) / ".workerbees"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "ledger.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")
        return True
    except Exception:
        return False


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agents-inc ledger")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("append", help="record a return row with an explicit verdict")
    a.add_argument("--node-id", required=True)
    a.add_argument("--verdict", choices=["pass", "fail"])
    a.add_argument("--status")
    a.add_argument("--run-id")
    a.add_argument("--seconds", type=float)
    a.add_argument("--subscription-calls", type=int)
    a.add_argument("--effort")
    a.add_argument("--input-tokens", type=int)
    a.add_argument("--output-tokens", type=int)
    a.add_argument("--cache-read", type=int)
    a.add_argument("--cache-write", type=int)
    a.add_argument("--file-created", action="append", dest="files_created")
    a.add_argument("--workspace")

    q = sub.add_parser("pending", help="list nodes still marked dispatched")
    q.add_argument("--workspace")
    return p


def cli(argv, state) -> int:
    """Run `append` or `pending`. Returns the process exit code."""
    try:
        args = _parser().parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    ws = Path(args.workspace) if args.workspace else host_workspace(state)

    if args.cmd == "pending":
        nodes = [n for n in ledger.load(ws).nodes.values() if n.status == "dispatched"]
        nodes.sort(key=lambda n: n.timestamp or "")
        for n in nodes:
            fields = [n.id, n.model, n.task, n.timestamp]
            print("\t".join("" if v is None else str(v).replace("\t", " ").replace("\n", " ")
                            for v in fields))
        return 0

    if args.verdict is None:
        print(_VERDICT_MSG, file=sys.stderr)
        return 2
    run_id = args.run_id
    if run_id is None:
        node = ledger.load(ws).nodes.get(args.node_id)
        run_id = node.run_id if node is not None else None
    if run_id is None:
        print(f"agents-inc ledger append: no dispatch row for node {args.node_id!r} "
              "and no --run-id given", file=sys.stderr)
        return 2
    status = args.status or ("verified" if args.verdict == "pass" else "red")
    ok = ledger.record_return(
        ws, node_id=args.node_id, status=status, seconds=args.seconds,
        subscription_calls=args.subscription_calls, run_id=run_id, effort=args.effort,
        input_tokens=args.input_tokens, output_tokens=args.output_tokens,
        cache_read=args.cache_read, cache_write=args.cache_write,
        files_created=args.files_created, verdict=args.verdict, store="jsonl")
    return 0 if ok else 1
