"""Host hook entry points. Advisory only: never block a session, always exit 0."""
from __future__ import annotations
import json, re, sys
from .doctor import check_install
from .paths import InstallPaths

NUDGE = ("agents-inc reminder: the Agent tool spawns Claude subagents only. Before delegating, route the task "
         "through agents-inc (workerbee skill): it picks the cheapest capable rung across Claude, Codex, Gemini, "
         "Mistral, and OpenRouter. Keep this Agent call only if routing selects a Claude rung.")

def session_start(paths: InstallPaths, host: str) -> str:
    report = check_install(paths)
    status = "READY" if report.ready else " ".join(report.codes)
    skill = paths.current / "skills/workerbee/SKILL.md"
    text = (f"agents-inc is installed (doctor: {status}). Every delegation in this session routes through agents-inc; "
            f"read {skill} before the first dispatch. Launcher: {paths.launcher}.")
    if not report.ready: text += " Tell the operator doctor is not READY and suggest `agents-inc repair --source <agents_Inc checkout>`."
    if host == "claude":
        return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}})
    return text

def agent_nudge(paths: InstallPaths, payload: dict) -> str:
    """Once per session, so a run of subagent spawns is not flooded with the same reminder."""
    session = re.sub(r"[^A-Za-z0-9_-]", "", str(payload.get("session_id") or "unknown"))[:128] or "unknown"
    marker = paths.state / "nudged" / session
    if marker.exists(): return ""
    marker.parent.mkdir(parents=True, exist_ok=True); marker.touch()
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": NUDGE}})

def run(paths: InstallPaths, event: str, host: str | None, stdin=sys.stdin) -> int:
    try:
        if event == "session-start": out = session_start(paths, host or "claude")
        elif event == "agent-nudge":
            raw = stdin.read()
            out = agent_nudge(paths, json.loads(raw) if raw.strip() else {})
        else: out = ""
        if out: print(out)
    except Exception as exc:  # a broken hook must never break the host session
        print(f"agents-inc hook {event}: {exc}", file=sys.stderr)
    return 0
