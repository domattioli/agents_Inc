"""D51 MCP transport: a stdio MCP server that fronts the dispatch broker for a Codex Lead.

Started by `agents-inc run --lead <run-dir>` as a child of the Codex process:
    python3 mcp_broker.py --run-dir <dir>
It shares validation and processing with the file broker (dispatch._validate_fields, _run_validated).
The run directory is broker-owned: no inbox, the Lead needs no write access. Standard library only.
"""
from __future__ import annotations
import argparse
import contextlib
import json
import math
import os
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agents_inc.install import dispatch as D  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "agents_inc", "version": "1"}
LOG_NAME = "mcp.log"
TOOLS = [
    {"name": "dispatch", "description": "Run one Worker through the credential-blind broker; blocks until done. "
     "Returns the result JSON and the Worker report.",
     "inputSchema": {"type": "object", "required": ["model", "effort", "slots"], "properties": {
         "model": {"type": "string"}, "effort": {"type": "string"},
         "slots": {"type": "object", "additionalProperties": {"type": "string"}}}}},
    {"name": "status", "description": "Return run.json counters and the remaining fan-out.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "wait", "description": "Return the stored result for a request_id, polling up to timeout seconds.",
     "inputSchema": {"type": "object", "required": ["request_id"], "properties": {
         "request_id": {"type": "string"}, "timeout": {"type": "number"}}}},
]


def log_line(run_dir: Path, text: str) -> None:
    """Append one line to <run-dir>/mcp.log; never follows a planted link."""
    line = f"{D._now()} {text}\n".encode("utf-8", "replace")
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(run_dir / LOG_NAME), flags, 0o644)
    except OSError:
        return
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


class Broker:
    def __init__(self, run_dir: Path, home_repo: str | None = None):
        self.run_dir = run_dir
        self.home_repo = home_repo
        self.issued: set = set()  # request ids this process issued; wait refuses any other
        self.spec = None  # loaded on the first tool call, so initialize and tools/list answer at once

    def ensure(self) -> None:
        if self.spec is None:
            self.spec = D._load_run_manifest(self.run_dir)
            D.init_broker_state(self.spec, transport="mcp")
            self.save()

    def save(self) -> None:
        D._atomic_write_json(self.run_dir / "run.json", self.spec, overwrite=True)

    def remaining(self) -> int:
        return max(0, self.spec["fan_out"]["total"] - self.spec["workers_spawned"])

    def tool_status(self, _args: dict) -> tuple[dict, bool, str]:
        self.ensure()
        data = {"workers_spawned": self.spec["workers_spawned"], "request_counts": self.spec["request_counts"],
                "fan_out": self.spec["fan_out"], "remaining_total": self.remaining(),
                "worker_models": self.spec["worker_models"]}
        return data, False, "ok"

    def tool_dispatch(self, args: dict) -> tuple[dict, bool, str]:
        self.ensure()
        rid = f"mcp-{int(time.time())}-{secrets.token_hex(3)}"
        self.issued.add(rid)
        model = args.get("model")
        req = {"schema_version": D.REQUEST_SCHEMA_VERSION, "request_id": rid, "model": model,
               "effort": args.get("effort"), "tier": D._load("dispatch_rungs").MODEL_RUNG.get(model)
               if isinstance(model, str) else None, "slots": args.get("slots")}
        if len(json.dumps(req).encode("utf-8")) > D.REQUEST_MAX_BYTES:
            req, reason = None, "oversize"
        else:
            req, reason = D._validate_fields(req, self.spec, rid)
        if req is None:
            self.spec["request_counts"]["refused"] += 1
            now = D._now()
            D._write_request_result(self.run_dir, rid, {
                "status": "refused", "dispatch_exit_code": D.REQ_REFUSED, "child_run_id": None, "outcome": None,
                "reason": reason, "started_at": now, "finished_at": now}, f"refused: {reason}\n")
            self.save()
            return {"status": "refused", "reason": reason, "request_id": rid}, True, f"refused:{reason}"
        result, report = D._run_validated(self.run_dir, rid, req, self.spec, self.home_repo)
        D._write_request_result(self.run_dir, rid, result, report)
        self.save()
        out = dict(result, request_id=rid, report=report)
        return out, result["status"] != "green", f"{result['status']}:{result.get('reason')}"

    def tool_wait(self, args: dict) -> tuple[dict, bool, str]:
        rid, timeout = args.get("request_id"), args.get("timeout", 60)
        if (not isinstance(rid, str) or not D.REQUEST_ID_RE.match(rid)
                or isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout)
                or timeout < 0):
            return {"status": "usage-error", "reason": "bad-request-id-or-timeout"}, True, "usage-error"
        if rid not in self.issued:
            return {"status": "refused", "reason": "unknown-request", "request_id": rid}, True, "refused:unknown-request"
        path = self.run_dir / f"{rid}.result.json"
        end = time.monotonic() + min(float(timeout), 3600.0)
        while not path.is_file() or path.is_symlink():
            if time.monotonic() >= end:
                return {"status": "timeout", "request_id": rid}, True, "timeout"
            time.sleep(0.5)
        data = json.loads(path.read_text(encoding="utf-8"))
        report = self.run_dir / f"{rid}.report.md"  # derived, never read from the result file
        inside = os.path.realpath(report).startswith(os.path.realpath(self.run_dir) + os.sep)
        data["report_path"] = str(report)
        data["report"] = report.read_text(encoding="utf-8") if inside and report.is_file() else ""
        return data, data.get("status") != "green", f"found:{data.get('status')}"


def _frames(stdin):
    """Yield (line, oversize) per stdin line without buffering more than the size limit plus one."""
    limit = D.REQUEST_MAX_BYTES
    while True:
        line = stdin.readline(limit + 2)
        if not line:
            return
        if len(line.encode("utf-8", "replace")) > limit + 1 and not line.endswith("\n"):
            while line and not line.endswith("\n"):  # discard the rest of the oversize frame
                line = stdin.readline(limit + 2)
            yield "", True
            continue
        yield line, len(line.encode("utf-8", "replace")) > limit + 1


def _reply(mid, result=None, error=None) -> dict:
    msg = {"jsonrpc": "2.0", "id": mid}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    return msg


def handle(broker: Broker, msg) -> dict | None:
    """Return the JSON-RPC reply for one parsed message, or None for a notification."""
    if not isinstance(msg, dict) or not isinstance(msg.get("method"), str):
        return _reply(msg.get("id") if isinstance(msg, dict) else None, error={"code": -32600, "message": "invalid request"})
    mid, method = msg.get("id"), msg["method"]
    if "id" not in msg:
        return None
    if method == "initialize":
        return _reply(mid, {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO})
    if method == "ping":
        return _reply(mid, {})
    if method == "tools/list":
        return _reply(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params")
        name = params.get("name") if isinstance(params, dict) else None
        args = params.get("arguments") if isinstance(params, dict) else None
        args = {} if args is None else args
        handler = {"dispatch": broker.tool_dispatch, "status": broker.tool_status, "wait": broker.tool_wait}.get(name)
        if handler is None or not isinstance(args, dict):
            return _reply(mid, error={"code": -32602, "message": "unknown tool or bad arguments"})
        try:
            data, is_error, note = handler(args)
        except Exception as exc:  # one bad call never stops the server
            data, is_error, note = {"status": "red", "reason": f"exception:{type(exc).__name__}"}, True, f"exception:{type(exc).__name__}"
        log_line(broker.run_dir, f"tool={name} {'error' if is_error else 'ok'} {note}")
        return _reply(mid, {"content": [{"type": "text", "text": json.dumps(data, indent=1)}], "isError": is_error})
    return _reply(mid, error={"code": -32601, "message": "method not found"})


def serve(run_dir: Path, stdin, stdout, log_env_keys: bool = True, home_repo: str | None = None) -> int:
    broker = Broker(run_dir, home_repo)
    logged = not log_env_keys
    for line, oversize in _frames(stdin):
        line = line.strip()
        if oversize:
            with contextlib.suppress(Exception):
                broker.ensure()
                broker.spec["request_counts"]["refused"] += 1
                broker.save()
            log_line(run_dir, "frame refused:oversize")
            stdout.write(json.dumps(_reply(None, error={"code": -32600, "message": "refused:oversize"})) + "\n")
            stdout.flush()
            continue
        if not line:
            continue
        try:
            reply = handle(broker, json.loads(line))
        except ValueError:
            reply = _reply(None, error={"code": -32700, "message": "parse error"})
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
        if not logged and reply is not None and "tools" in (reply.get("result") or {}):
            logged = True  # after the first tools/list reply; names only, never values
            log_line(run_dir, "env-keys: " + ",".join(sorted(os.environ)))
    return D.BROKER_OK


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="mcp_broker")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--home-repo")
    args = parser.parse_args(argv)
    root = Path(args.run_dir)
    if root.is_symlink() or not root.is_dir():
        print(f"mcp_broker: run directory missing: {args.run_dir}", file=sys.stderr)
        return D.BROKER_USAGE
    proto_out = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)  # stray prints from dispatch internals go to stderr, never into the protocol stream
    return serve(root.resolve(), sys.stdin, proto_out, home_repo=args.home_repo)


if __name__ == "__main__":
    raise SystemExit(main())
