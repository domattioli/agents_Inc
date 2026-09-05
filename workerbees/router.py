"""Pick a Worker model for a task. Model IDs live only in routing.json."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

_TABLE = json.loads((Path(__file__).parent / "routing.json").read_text())

@dataclass(frozen=True)
class Route:
    provider: str
    model: str
    tier: str
    cmd_kind: str  # "cli" for claude/codex, "http" for optional providers

def pick_model(task: str, tier: str, available: set[str], workspace_authorized: bool,
               exclude_provider: str | None = None, prefer_provider: str | None = None) -> Route | None:
    models = _TABLE["tiers"].get(tier)
    if not models:
        return None
    order = _TABLE["required"] + _TABLE["optional"]
    # Try preferred provider first if eligible
    if prefer_provider is not None and prefer_provider in available:
        if prefer_provider in models and prefer_provider != exclude_provider:
            if prefer_provider not in _TABLE["optional"] or (workspace_authorized and task in _TABLE["optional_allowed_tasks"]):
                kind = "cli" if prefer_provider in _TABLE["required"] else "http"
                return Route(prefer_provider, models[prefer_provider], tier, kind)
    # Fall back to normal order
    for provider in order:
        if provider not in available or provider not in models or provider == exclude_provider:
            continue
        if provider in _TABLE["optional"]:
            if not workspace_authorized or task not in _TABLE["optional_allowed_tasks"]:
                continue
        kind = "cli" if provider in _TABLE["required"] else "http"
        return Route(provider, models[provider], tier, kind)
    return None
