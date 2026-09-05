"""Preflight: probe each Required provider CLI; cache results; feed the router. No auth files touched."""
from __future__ import annotations
import json, re, time, uuid
from pathlib import Path
from .adapters import claude, codex
from .adapters.base import run_worker
from .keys import ENV_PATH, available_providers, REQUIRED
from .router import _TABLE
from . import ledger

_AUTH = re.compile(r"not logged in|/login|unauthori[sz]ed|auth", re.I)

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def probe_cli(provider: str, runner=run_worker, workspace: Path | None = None, run_id: str | None = None) -> dict:
    model = _TABLE["tiers"]["cheap"][provider]
    cmd = claude.build_cmd(model) if provider == "claude" else codex.build_cmd(model)

    # Record probe dispatch and return (T020) if workspace provided
    probe_node_id = None
    start_time = time.monotonic()
    if workspace and run_id:
        probe_node_id = uuid.uuid4().hex
        ledger.record_dispatch(workspace, node_id=probe_node_id, run_id=run_id, model=model,
                              tier="cheap", task="probe", provider=provider,
                              parent_id=None, edge_type="probes")

    res = runner(cmd, "reply exactly PONG")

    if probe_node_id and workspace and run_id:
        elapsed = time.monotonic() - start_time
        # Map probe result to a ledger status
        text = (res.output or "") + (res.stderr or "")
        if res.exit_code == 127 or "WB_CLI_NOT_FOUND" in text:
            status_str = "failed"
        elif res.status == "paused":
            status_str = "paused"
        elif "PONG" in res.output:
            status_str = "returned"
        elif _AUTH.search(text):
            status_str = "blocked"
        else:
            status_str = "failed"
        ledger.record_return(workspace, node_id=probe_node_id, status=status_str, seconds=elapsed, subscription_calls=1)

    text = (res.output or "") + (res.stderr or "")
    if res.exit_code == 127 or "WB_CLI_NOT_FOUND" in text:
        status = "WB_CLI_NOT_FOUND"
    elif res.status == "paused":
        status = "WB_QUOTA_EXHAUSTED"
    elif "PONG" in res.output:
        status = "ok"
    elif _AUTH.search(text):
        status = "WB_AUTH_REQUIRED"
    else:
        status = "WB_CLI_UNSUPPORTED"
    return {"provider": provider, "status": status, "detail": text[-300:], "at": _now()}

def run(workspace: Path, providers=("claude", "codex"), runner=run_worker) -> dict:
    # Generate run_id for this doctor run (groups all probes)
    run_id = uuid.uuid4().hex
    results = {p: probe_cli(p, runner=runner, workspace=workspace, run_id=run_id) for p in providers}
    paused = [p for p, r in results.items() if r["status"] == "WB_QUOTA_EXHAUSTED"]
    out = {"results": results, "paused": paused, "at": _now(), "epoch": time.time()}
    d = workspace / ".workerbees"; d.mkdir(parents=True, exist_ok=True)
    (d / "doctor.json").write_text(json.dumps(out, indent=2))
    return out

def available(workspace: Path, env_path: Path = ENV_PATH, max_age_s: int = 3600, runner=run_worker, extra_env_paths: list | None = None) -> set[str]:
    f = workspace / ".workerbees" / "doctor.json"
    cache = None
    if f.exists():
        try:
            cache = json.loads(f.read_text())
            if time.time() - float(cache.get("epoch", 0)) > max_age_s:
                cache = None
        except (json.JSONDecodeError, OSError, ValueError):
            cache = None
    if cache is None:
        cache = run(workspace, runner=runner)
    ok_required = {p for p, r in cache["results"].items() if r["status"] == "ok"}
    return (available_providers(env_path, extra_env_paths=extra_env_paths) - REQUIRED) | ok_required

def quota_paused(workspace: Path) -> list[str]:
    f = workspace / ".workerbees" / "doctor.json"
    if not f.exists():
        return []
    try:
        cache = json.loads(f.read_text())
        return cache.get("paused", [])
    except (json.JSONDecodeError, OSError):
        return []
