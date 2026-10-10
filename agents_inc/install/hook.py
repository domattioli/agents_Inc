"""Host hook entry points. Advisory, except the FR-002 persona deny; never break a session, always exit 0."""
from __future__ import annotations
import hashlib, json, os, re, sys, tempfile, time
from datetime import datetime
from .doctor import check_install
from .paths import InstallPaths

NUDGE = ("agents-inc reminder: the Agent tool spawns Claude subagents only. Before delegating, route the task "
         "through agents-inc (workerbee skill): it picks the cheapest capable rung across Claude, Codex, Gemini, "
         "Mistral, and OpenRouter. Keep this Agent call only if routing selects a Claude rung.")
# Spec 015 FR-002: a Codex persona name at the start of a Claude subagent description mislabels the model.
PERSONA_RE = re.compile(r"(?i)\A(?:astra|sol|terra|luna)(?=\s|:|/|\Z)")
PERSONA_DENY_REASON = ("FR-002: Agent/Task descriptions cannot begin with a Codex persona name. For Codex execution, "
                       "dispatch through agents-inc; Agent/Task creates Claude subagents. If this names a product, "
                       "repository, person, or supervised worker, put the actual Claude rung first and mention that "
                       "name later. Renaming does not change the execution model.")
AGENT_TOOLS = {"Agent", "Task"}
FAN_OUT = "agents-inc: fan-out"
INFLIGHT_TTL_S = 7200  # a spawn that never reports done stops warning after 2 h
DISPATCH_RE = re.compile(r"agents-inc\s+dispatch|\b(?:gask|mask|oask|agent)\.sh\b|\bcodex\s+exec\b")
DELEGATE_RE = re.compile(r"\Amcp__.*__DelegateAgent\Z")
QUICKREF_HEADER = ("agents-inc quickref (skills/workerbee/QUICKREF.md, loaded once per session on first dispatch; full "
                   "SKILL.md still required for non-Claude rungs, prompts from scratch, or disputed gates):")

def session_start(paths: InstallPaths, host: str) -> str:
    report = check_install(paths)
    status = "READY" if report.ready else " ".join(report.codes)
    skill = paths.current / "skills/workerbee/SKILL.md"
    text = (f"agents-inc is installed (doctor: {status}). Every delegation in this session routes through agents-inc; "
            f"read {skill} before the first dispatch. Launcher: {paths.launcher}.")
    if not report.ready: text += " Tell the operator doctor is not READY and suggest `agents-inc repair --source <agents_Inc checkout>`."
    from .update_check import notice  # at most one PyPI request a day; silent on any failure
    update = notice(paths.state)
    if update: text += " " + update + " Tell the operator once; do not update without their go-ahead."
    if host == "claude":
        return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}})
    return text

def _session(payload: dict) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", str(payload.get("session_id") or "unknown"))[:128] or "unknown"

def _tool_input(payload: dict) -> dict:
    value = payload.get("tool_input")
    return value if isinstance(value, dict) else {}

def _context(*texts: str) -> str:
    texts = [t for t in texts if t]
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "\n\n".join(texts)}}) if texts else ""

def _nudge_text(paths: InstallPaths, payload: dict) -> str:
    marker = paths.state / "nudged" / _session(payload)
    if marker.exists(): return ""
    marker.parent.mkdir(parents=True, exist_ok=True); marker.touch()
    return NUDGE

def _is_dispatch(payload: dict) -> bool:
    tool = str(payload.get("tool_name") or "")
    if tool in AGENT_TOOLS or DELEGATE_RE.match(tool): return True
    return tool == "Bash" and bool(DISPATCH_RE.search(str(_tool_input(payload).get("command") or "")))

def _quickref_text(paths: InstallPaths, payload: dict) -> str:
    """Once per session, on the first dispatch-shaped call; a missing file yields a note, never an error."""
    marker = paths.state / "quickref" / _session(payload)
    if marker.exists(): return ""
    marker.parent.mkdir(parents=True, exist_ok=True); marker.touch()
    source = paths.current / "skills/workerbee/QUICKREF.md"
    try: return f"{QUICKREF_HEADER}\n\n{source.read_text(encoding='utf-8')}"
    except OSError: return f"agents-inc quickref missing: {source} not found; read skills/workerbee/SKILL.md before dispatching."

def agent_nudge(paths: InstallPaths, payload: dict) -> str:
    """Once per session, so a run of subagent spawns is not flooded with the same reminder."""
    return _context(_nudge_text(paths, payload))

def persona_deny(payload: object) -> str:
    """The only blocking path. Anything unexpected fails open (empty string)."""
    try:
        if not isinstance(payload, dict) or payload.get("tool_name") not in AGENT_TOOLS: return ""
        description = _tool_input(payload).get("description")
        if not isinstance(description, str) or not PERSONA_RE.match(description): return ""
        return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                  "permissionDecisionReason": PERSONA_DENY_REASON}})
    except Exception:
        return ""

def task_key(payload: dict) -> str:
    def norm(value): return " ".join(str(value or "").lower().split())
    tool_input = _tool_input(payload)
    return hashlib.sha256((norm(tool_input.get("description")) + "\n" + norm(tool_input.get("prompt"))).encode()).hexdigest()[:16]

def _inflight(paths: InstallPaths, key: str): return paths.state / "inflight" / f"{key}.json"

def _read_entry(path) -> dict | None:
    try: entry = json.loads(path.read_text())
    except (OSError, ValueError): return None
    return entry if isinstance(entry, dict) else None

def _write_entry(path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out: json.dump(entry, out)
        os.replace(raw, path)
    finally:
        if os.path.exists(raw): os.unlink(raw)

def duplicate_check(paths: InstallPaths, payload: dict) -> str:
    """Warn when another live session spawned the same task; then claim the task for this session."""
    if payload.get("tool_name") not in AGENT_TOOLS or FAN_OUT in str(_tool_input(payload).get("prompt") or ""): return ""
    key, session, now = task_key(payload), _session(payload), time.time()
    path, warning = _inflight(paths, key), ""
    try:
        entry = _read_entry(path)
        if entry and entry.get("expires", 0) > now and entry.get("session_id") != session:
            since = datetime.fromtimestamp(entry.get("started", now)).strftime("%Y-%m-%d %H:%M")
            warning = (f"agents-inc duplicate warning: the same task (key {key}) is in flight from session "
                       f"{entry.get('session_id')} since {since}. If this is intentional fan-out, add the line "
                       f"\"{FAN_OUT}\" to the prompt.")
        _write_entry(path, {"session_id": session, "tool_use_id": payload.get("tool_use_id"),
                            "started": now, "expires": now + INFLIGHT_TTL_S})
    except OSError as exc:
        print(f"agents-inc hook agent-nudge: in-flight registry unavailable: {exc}", file=sys.stderr)
    return warning

def agent_done(paths: InstallPaths, payload: dict) -> None:
    """Record a host-ledger dispatch row (spec 016), then release this session's claim when a foreground
    Agent/Task spawn returns; a background launch returns at once, so its claim stays until the TTL."""
    try:
        from .. import host_ledger  # lazy: a broken ledger import must not break the other hook events
        host_ledger.record_hook_dispatch(paths.state, payload)
    except Exception:
        pass
    if payload.get("tool_name") not in AGENT_TOOLS or _tool_input(payload).get("run_in_background") is True: return
    path = _inflight(paths, task_key(payload))
    entry = _read_entry(path)
    if entry and entry.get("session_id") == _session(payload): path.unlink(missing_ok=True)

def _payload(stdin) -> dict:
    raw = stdin.read()
    try: payload = json.loads(raw) if raw.strip() else {}
    except ValueError: return {}
    return payload if isinstance(payload, dict) else {}

def run(paths: InstallPaths, event: str, host: str | None, stdin=sys.stdin) -> int:
    try:
        out = ""
        if event == "session-start": out = session_start(paths, host or "claude")
        elif event == "agent-nudge":
            payload = _payload(stdin)
            if _is_dispatch(payload):  # the Bash matcher sees every command; only dispatch-shaped calls get context
                nudge = _nudge_text(paths, payload) if payload.get("tool_name") in AGENT_TOOLS else ""  # NUDGE wording is Agent-only
                out = persona_deny(payload) or _context(nudge, _quickref_text(paths, payload), duplicate_check(paths, payload))
        elif event == "agent-done": agent_done(paths, _payload(stdin))
        if out: print(out)
    except Exception as exc:  # a broken hook must never break the host session
        print(f"agents-inc hook {event}: {exc}", file=sys.stderr)
    return 0
