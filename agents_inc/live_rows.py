"""Spec 027: turn live delegate events (<run dir>/events.jsonl) into redacted one-line rows for a person.

render() maps one event envelope to rows (FR-014), redact() strips secrets (FR-015), follow() tails the file and
prints batches of rows (FR-013, FR-016). Row text is for people: the relay mod appends it to a transcript."""
from __future__ import annotations
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from .install.report import SECRET_RE

REDACTED = "[redacted]"
ROW_CAP = 240  # characters of one row (FR-014)
THINK_CAP = 120  # characters of a `think` summary (FR-014)
RAW_CAP = 120  # characters of a non-JSON provider line shown in a `note` row
_SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD")
_EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def redact(text: str, env=None, home=None) -> str:
    """FR-015: SECRET_RE matches, then values of KEY/TOKEN/SECRET/PASSWORD variables (8+ characters), become
    [redacted]; the home directory becomes ~. env and home default to the process's own."""
    env = os.environ if env is None else env
    text = SECRET_RE.sub(REDACTED, text)
    values = {v for k, v in env.items() if _SECRET_NAME.search(k.upper()) and isinstance(v, str) and len(v) >= 8}
    for value in sorted(values, key=len, reverse=True):
        text = text.replace(value, REDACTED)
    home = str(Path.home()) if home is None else str(home)
    if len(home) > 1:
        text = text.replace(home.rstrip("/"), "~")
    return text


def parse_ts(ts) -> float:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _keys(value) -> str:
    return ", ".join(str(k) for k in value) if isinstance(value, dict) else ""


def _named(name: str, args) -> str:
    keys = _keys(args)
    return f"{name} ({keys})" if keys else name


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _codex_item(ev: dict) -> list:
    item = ev.get("item") if isinstance(ev.get("item"), dict) else {}
    kind = item.get("type")
    started = ev.get("type") == "item.started"
    if kind == "command_execution":
        exit_code = item.get("exit_code")
        suffix = f" (exit {exit_code})" if isinstance(exit_code, int) and not isinstance(exit_code, bool) else ""
        return [("tool", f"{_text(item.get('command'))}{suffix}")]
    if started:  # a started item is shown once, when it completes
        return []
    if kind == "agent_message":
        return [("say", _text(item.get("text")))]
    if kind == "reasoning":
        return [("think", _text(item.get("text")))]
    if kind == "file_change":
        changes = item.get("changes") if isinstance(item.get("changes"), list) else []
        return [("file", ", ".join(_text(c.get("path")) for c in changes if isinstance(c, dict)))]
    if kind == "mcp_tool_call":
        return [("tool", _named(f"{_text(item.get('server'))}.{_text(item.get('tool'))}", item.get("arguments")))]
    return [("note", f"codex {ev.get('type')}")]


def _usage(ev: dict) -> list:
    usage = ev.get("usage") if isinstance(ev.get("usage"), dict) else {}
    return [("usage", f"in={usage.get('input_tokens', 0)} out={usage.get('output_tokens', 0)}")]


def _codex(ev: dict) -> list:
    kind = ev.get("type")
    if kind in ("item.started", "item.completed"):
        return _codex_item(ev)
    if kind == "error":
        return [("error", _text(ev.get("message")))]
    if kind == "turn.failed":
        err = ev.get("error")
        return [("error", _text(err.get("message") if isinstance(err, dict) else err))]
    if kind == "turn.completed":
        return _usage(ev)
    return [("note", f"codex {kind}")]


def _claude_block(block: dict) -> list:
    kind = block.get("type")
    if kind == "text":
        return [("say", _text(block.get("text")))]
    if kind == "thinking":
        return [("think", _text(block.get("thinking")))]
    if kind == "tool_use":
        name, args = _text(block.get("name")), block.get("input") if isinstance(block.get("input"), dict) else {}
        if name == "Bash":
            return [("tool", _text(args.get("command")))]
        if name in _EDIT_TOOLS:
            return [("file", _text(args.get("file_path") or args.get("notebook_path")))]
        return [("tool", _named(name, args))]
    return []


def _claude(ev: dict) -> list:
    kind = ev.get("type")
    if kind == "assistant":
        message = ev.get("message") if isinstance(ev.get("message"), dict) else {}
        blocks = message.get("content") if isinstance(message.get("content"), list) else []
        return [row for b in blocks if isinstance(b, dict) for row in _claude_block(b)]
    if kind == "result":
        if ev.get("is_error"):
            return [("error", _text(ev.get("result")) or _text(ev.get("subtype")) or "error")]
        return _usage(ev)
    return [("note", f"claude {kind}")]


def _summaries(source: str, ev: dict) -> list:
    """(kind, summary) pairs for one event (FR-014 table)."""
    kind = ev.get("type")
    if kind == "raw":
        return [("note", f"{source} raw: {_text(ev.get('text'))[:RAW_CAP]}")]
    if source == "agents-inc" and kind == "run.start":
        return [("start", f"run {ev.get('run_id')}")]
    if source == "agents-inc" and kind == "run.end":
        return [("end", f"{ev.get('outcome')} rc={ev.get('rc')}")]
    if source == "codex":
        return _codex(ev)
    if source == "claude":
        return _claude(ev)
    return [("note", f"{source} {kind}")]


def render(envelope: dict, model: str, t0: float, env=None, home=None) -> list:
    """Rows for one event envelope: `[MM:SS] <model> <kind>: <summary>`, MM:SS the time since t0 (epoch seconds).
    Whitespace collapses, secrets are redacted, a row over 240 characters is cut to 239 plus `…`."""
    event = envelope.get("event") if isinstance(envelope.get("event"), dict) else {}
    elapsed = max(0, int(parse_ts(envelope.get("ts")) - t0))
    stamp = f"[{elapsed // 60:02d}:{elapsed % 60:02d}]"
    rows = []
    for kind, summary in _summaries(str(envelope.get("source")), event):
        summary = redact(" ".join(summary.split()), env, home)  # redact before any cut: no half secret survives
        if kind == "think":
            summary = summary[:THINK_CAP]
        row = f"{stamp} {model} {kind}: {summary}"
        rows.append(row if len(row) <= ROW_CAP else row[:ROW_CAP - 1] + "…")
    return rows


class SystemClock:
    now = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)


def follow(run_dir, out, clock=None, interval: float = 1.0, batch: int = 20, poll: float = 0.2, wait: float = 30.0,
           env=None, home=None) -> int:
    """Tail <run dir>/events.jsonl by byte offset and print rendered rows to out in batches separated by an empty line:
    a batch at most once per `interval` seconds, or at once when `batch` rows wait (FR-016). Return 0 after `run.end`,
    3 when no events.jsonl appears within `wait` seconds (FR-013). clock has now() and sleep(seconds)."""
    clock = clock or SystemClock()
    path = Path(run_dir) / "events.jsonl"
    began, offset, partial = clock.now(), 0, b""
    model, t0 = "?", None
    pending: list = []
    last_flush = None

    def flush(count: int) -> None:
        nonlocal last_flush
        chunk = pending[:count]
        del pending[:count]
        if chunk:
            out.write("\n".join(chunk) + "\n\n")
            out.flush()
        last_flush = clock.now()

    seen = False
    while True:
        try:
            with open(path, "rb") as fh:
                fh.seek(offset)
                data = fh.read()
            seen = True
        except OSError:
            data = b""
            if not seen and clock.now() - began >= wait:
                return 3
        offset += len(data)
        *lines, partial = (partial + data).split(b"\n")  # the last piece may be half a line: keep it
        done = False
        for raw in lines:
            try:
                env_line = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(env_line, dict):
                continue
            event = env_line.get("event") if isinstance(env_line.get("event"), dict) else {}
            if t0 is None:
                t0 = parse_ts(env_line.get("ts"))
            if env_line.get("source") == "agents-inc" and event.get("type") == "run.start":
                model, t0 = str(event.get("model") or "?"), parse_ts(env_line.get("ts"))
            pending.extend(render(env_line, model, t0, env, home))
            if env_line.get("source") == "agents-inc" and event.get("type") == "run.end":
                done = True
                break
        while len(pending) >= batch:
            flush(batch)
        if done:
            while pending:
                flush(batch)
            return 0
        if pending and (last_flush is None or clock.now() - last_flush >= interval):
            flush(batch)
        clock.sleep(poll)
