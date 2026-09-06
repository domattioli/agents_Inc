"""Preflight: probe each Required provider CLI; cache results; feed the router. No auth files touched."""
from __future__ import annotations
import json, re, time, uuid, os
from pathlib import Path
from datetime import datetime
from .adapters import claude, codex
from .adapters.base import run_worker
from .keys import ENV_PATH, available_providers, REQUIRED
from .router import _TABLE
from . import ledger

_AUTH = re.compile(r"not logged in|/login|unauthori[sz]ed|auth", re.I)

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def probe_cli(provider: str, runner=run_worker, workspace: Path | None = None, run_id: str | None = None, *,
              governance_mode: str | None = None, gateway=None, registry=None) -> dict:
    gov_mode = governance_mode if governance_mode is not None else os.environ.get("WORKERBEES_GOVERNANCE", "off")
    if gov_mode not in ("off", "shadow", "enforce"):
        raise ValueError(f"Invalid WORKERBEES_GOVERNANCE mode: {gov_mode}")

    model = _TABLE["tiers"]["cheap"][provider]

    if gov_mode == "off":
        # Original behavior: direct run with ledger calls by doctor
        cmd = claude.build_cmd(model) if provider == "claude" else codex.build_cmd(model)
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
            text = (res.output or "") + (res.stderr or "")
            status_str = ("failed" if (res.exit_code == 127 or "WB_CLI_NOT_FOUND" in text)
                         else "paused" if res.status == "paused"
                         else "returned" if "PONG" in res.output
                         else "blocked" if _AUTH.search(text)
                         else "failed")
            ledger.record_return(workspace, node_id=probe_node_id, status=status_str, seconds=elapsed, subscription_calls=1)
    else:
        # shadow/enforce: gateway handles ledger
        if gateway is None:
            return {"provider": provider, "status": "WB_GOVERNANCE_NO_GATEWAY",
                   "detail": "governed mode requires a gateway", "at": _now()}
        from .envelope import Envelope
        from .router import pick_model
        uid = uuid.uuid4().hex
        env = Envelope(message_id=uid, task_id=uid, parent_task_id=None, correlation_id=uid,
            sender="agent-supervisor-01", recipient="agent-doctor-01", intent="probe", operation="request",
            protocol="v1", schema="request_v1", payload={"prompt": "reply exactly PONG"},
            data_classification="public", created_at=datetime.utcnow().isoformat()+"Z")
        route = pick_model("probe", "cheap", {provider}, False)
        if route is None:
            return {"provider": provider, "status": "WB_NO_ELIGIBLE_ROUTE",
                   "detail": "no eligible route for probe", "at": _now()}
        result = gateway.dispatch(env, context={"authenticated_sender": env.sender, "run_id": run_id or uuid.uuid4().hex,
            "parent_id": None, "edge_type": "probes"}, runner=runner, route=route)
        if result.status != "allowed":
            d = result.decision
            return {"provider": provider, "status": "WB_GOVERNANCE_" + result.status.upper(),
                   "detail": d.reason if d else "unknown", "at": _now()}
        res = result.worker_result

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

def run(workspace: Path, providers=("claude", "codex"), runner=run_worker, *,
        governance_mode: str | None = None, gateway=None, registry=None) -> dict:
    run_id = uuid.uuid4().hex
    results = {p: probe_cli(p, runner=runner, workspace=workspace, run_id=run_id,
                           governance_mode=governance_mode, gateway=gateway, registry=registry)
              for p in providers}
    paused = [p for p, r in results.items() if r["status"] == "WB_QUOTA_EXHAUSTED"]
    out = {"results": results, "paused": paused, "at": _now(), "epoch": time.time()}
    d = workspace / ".workerbees"; d.mkdir(parents=True, exist_ok=True)
    (d / "doctor.json").write_text(json.dumps(out, indent=2))
    return out

def available(workspace: Path, env_path: Path = ENV_PATH, max_age_s: int = 3600, runner=run_worker, extra_env_paths: list | None = None, *,
              governance_mode: str | None = None, gateway=None, registry=None) -> set[str]:
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
        cache = run(workspace, runner=runner, governance_mode=governance_mode, gateway=gateway, registry=registry)
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
