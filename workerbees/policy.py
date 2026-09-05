"""Governance checks run BEFORE any dispatch. Spend cap is structural: no paid path exists."""
from __future__ import annotations
import json
from pathlib import Path
from .router import Route, _TABLE

class PolicyError(Exception):
    """Dispatch refused by policy. Message is user-facing."""

def is_authorized(workspace: Path) -> bool:
    f = workspace / ".workerbees" / "authorization.json"
    if not f.exists():
        return False
    try:
        return bool(json.loads(f.read_text()).get("optional_providers"))
    except (json.JSONDecodeError, OSError):
        return False

def check_dispatch(route: Route, workspace: Path, confidential: bool) -> None:
    if route.provider in _TABLE["optional"] and confidential and not is_authorized(workspace):
        raise PolicyError(
            f"WB_WORKSPACE_AUTH_REQUIRED: {route.provider} may not receive confidential input; "
            f"grant per-workspace authorization in {workspace}/.workerbees/authorization.json")

def paused(reason: str) -> dict:
    return {"status": "paused", "reason": reason,
            "message": "Quota exhausted. Job paused; no paid fallback exists. Retry later."}
