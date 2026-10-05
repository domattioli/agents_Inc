"""D54 Worker-to-Lead channel: a stdio MCP server with one tool, ask_lead(question).

The broker copies this file into the Worker's child run directory and starts it for the Worker:
    python3 worker_mcp.py --run-dir <child>/ask --request-id <id>
ask_lead writes <run-dir>/<id>.question.<n>.json and waits up to 30 minutes for <id>.answer.<n>.json, which the
broker writes when the Lead calls answer. The Worker sees only ask_lead: never dispatch, status, wait, resume or
answer. Standalone and standard library only, because the copy runs without the agents_inc package.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "agents_inc", "version": "1"}
QUESTION_MAX_BYTES = 16 * 1024
FRAME_MAX_BYTES = 64 * 1024
ANSWER_MAX_BYTES = 128 * 1024
WAIT_SEC = 1800.0
POLL_SEC = 2.0
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
NO_ANSWER = "no answer from Lead after 30 minutes; decide or stop"
TOOLS = [
    {"name": "ask_lead", "description": "Ask your Lead one question and wait up to 30 minutes for the answer. "
     "Use it when the task is ambiguous or blocked; the Lead cannot message you any other way.",
     "annotations": {"readOnlyHint": True},
     "inputSchema": {"type": "object", "required": ["question"], "properties": {
         "question": {"type": "string", "description": "One plain question, at most 16 KiB."}}}},
]


class Channel:
    def __init__(self, run_dir: Path, request_id: str, sleep=time.sleep, clock=time.monotonic,
                 wait_sec: float = WAIT_SEC, poll_sec: float = POLL_SEC):
        self.run_dir, self.rid = run_dir, request_id
        self.sleep, self.clock, self.wait_sec, self.poll_sec = sleep, clock, wait_sec, poll_sec

    def _next_n(self) -> int:
        n = 1
        while os.path.lexists(str(self.run_dir / f"{self.rid}.question.{n}.json")):
            n += 1
        return n

    def _write_question(self, question: str) -> int:
        """Write the next question file atomically; never overwrite, never follow a link. Return its number."""
        text = json.dumps({"question": question, "asked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        tmp = self.run_dir / f".{self.rid}.question.{secrets.token_hex(4)}.tmp"
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
            for _ in range(100):
                n = self._next_n()
                try:
                    os.link(str(tmp), str(self.run_dir / f"{self.rid}.question.{n}.json"))
                    return n
                except FileExistsError:
                    continue
            raise OSError("no free question number")
        finally:
            try:
                os.unlink(str(tmp))
            except OSError:
                pass

    def _read_answer(self, n: int):
        try:
            fd = os.open(str(self.run_dir / f"{self.rid}.answer.{n}.json"), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError:
            return None
        with os.fdopen(fd, "rb") as fh:
            raw = fh.read(ANSWER_MAX_BYTES + 1)
        try:
            answer = json.loads(raw.decode("utf-8")).get("answer")
        except (ValueError, AttributeError, UnicodeDecodeError):
            return None  # partial or foreign file: keep waiting
        return answer if isinstance(answer, str) else None

    def ask(self, question) -> tuple[str, bool]:
        """Return (text for the Worker, is_error)."""
        if not isinstance(question, str) or not question.strip():
            return "ask_lead needs a non-empty question string", True
        if len(question.encode("utf-8")) > QUESTION_MAX_BYTES:
            return f"question too long: at most {QUESTION_MAX_BYTES} bytes", True
        n = self._write_question(question)
        end = self.clock() + self.wait_sec
        while True:
            answer = self._read_answer(n)
            if answer is not None:
                return answer, False
            if self.clock() >= end:
                return NO_ANSWER, False
            self.sleep(self.poll_sec)


def _reply(mid, result=None, error=None) -> dict:
    msg = {"jsonrpc": "2.0", "id": mid}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    return msg


def handle(channel: Channel, msg) -> dict | None:
    """Return the JSON-RPC reply for one parsed message, or None for a notification."""
    if not isinstance(msg, dict) or not isinstance(msg.get("method"), str):
        return _reply(msg.get("id") if isinstance(msg, dict) else None, error={"code": -32600, "message": "invalid request"})
    if "id" not in msg:
        return None
    mid, method = msg["id"], msg["method"]
    if method == "initialize":
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        version = params.get("protocolVersion") if isinstance(params.get("protocolVersion"), str) else PROTOCOL_VERSION
        return _reply(mid, {"protocolVersion": version, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO})
    if method == "ping":
        return _reply(mid, {})
    if method == "tools/list":
        return _reply(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params")
        name = params.get("name") if isinstance(params, dict) else None
        args = params.get("arguments") if isinstance(params, dict) else None
        if name != "ask_lead" or not isinstance(args, dict):
            return _reply(mid, error={"code": -32602, "message": "unknown tool or bad arguments"})
        try:
            text, is_error = channel.ask(args.get("question"))
        except OSError as exc:
            text, is_error = f"ask_lead failed: {type(exc).__name__}", True
        return _reply(mid, {"content": [{"type": "text", "text": text}], "isError": is_error})
    return _reply(mid, error={"code": -32601, "message": "method not found"})


def serve(channel: Channel, stdin, stdout) -> int:
    while True:
        line = stdin.readline(FRAME_MAX_BYTES + 2)
        if not line:
            return 0
        if len(line.encode("utf-8", "replace")) > FRAME_MAX_BYTES + 1:
            while line and not line.endswith("\n"):
                line = stdin.readline(FRAME_MAX_BYTES + 2)
            reply = _reply(None, error={"code": -32600, "message": "refused:oversize"})
        elif not line.strip():
            continue
        else:
            try:
                reply = handle(channel, json.loads(line))
            except ValueError:
                reply = _reply(None, error={"code": -32700, "message": "parse error"})
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="worker_mcp")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--request-id", required=True)
    args = parser.parse_args(argv)
    root = Path(args.run_dir)
    if root.is_symlink() or not root.is_dir() or not REQUEST_ID_RE.match(args.request_id):
        print("worker_mcp: bad --run-dir or --request-id", file=sys.stderr)
        return 2
    return serve(Channel(root.resolve(), args.request_id), sys.stdin, sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
