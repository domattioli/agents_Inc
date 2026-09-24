"""Pick catalog-eligible Worker models. routing.json sets provider order and defaults."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

_TABLE = json.loads((Path(__file__).parent / "routing.json").read_text())
_CATALOG = json.loads((Path(__file__).parent / "models.json").read_text())["models"]
_AUTO_FREE = "openrouter/auto:free"

@dataclass(frozen=True)
class Route:
    provider: str
    model: str
    tier: str
    cmd_kind: str  # "cli" for claude/codex, "http" for optional providers

def _eligible(model: str, task: str, *, require_good: bool = False) -> bool:
    profile = _CATALOG.get(model)
    if not profile or profile.get("status") == "unavailable":
        return False
    if task in profile.get("tasks_bad", []):
        return False
    return not require_good or task in profile.get("tasks_good", [])

def _remap_codex(model: str, model_map: dict[str, str] | None = None) -> str:
    """Apply a user nickname override (roster/env) to a routing.json codex slug, on read only."""
    from .install.runtime import MODEL_ALIASES, load_model_map
    model_map = load_model_map() if model_map is None else model_map
    for nick, default in MODEL_ALIASES.items():
        if model == default:
            return model_map.get(nick, default)
    return model

def _provider_routes(provider: str, task: str, tier: str) -> list[Route]:
    if provider == "openrouter":
        named = [
            Route(provider, model, tier, "http")
            for model, profile in _CATALOG.items()
            if model != _AUTO_FREE
            and profile.get("provider") == provider
            and profile.get("tier") == tier
            and _eligible(model, task, require_good=True)
        ]
        if _eligible(_AUTO_FREE, task, require_good=True):
            named.append(Route(provider, _AUTO_FREE, tier, "http"))
        return named
    configured = _TABLE["tiers"].get(tier, {}).get(provider)
    models = configured if isinstance(configured, list) else [configured]
    if provider == "codex":
        models = [_remap_codex(m) if m else m for m in models]
    kind = "cli" if provider in _TABLE["required"] else "http"
    return [Route(provider, model, tier, kind) for model in models
            if model and _eligible(model, task)]

def pick_model_chain(task: str, tier: str, available: set[str], workspace_authorized: bool,
                     exclude_provider: str | None = None,
                     prefer_provider: str | None = None, local_authorized: bool = False,
                     local_only: bool = False) -> tuple[Route, ...]:
    """Return bounded candidates in retry order. OpenRouter auto:free is always last."""
    if tier not in _TABLE["tiers"]:
        return ()
    order = list(_TABLE["required"] + _TABLE["optional"])
    if prefer_provider in order:
        order.remove(prefer_provider)
        order.insert(0, prefer_provider)

    # If local_only, restrict to ollama only
    if local_only:
        order = ["ollama"]

    routes: list[Route] = []
    for provider in order:
        if provider not in available or provider == exclude_provider:
            continue
        if provider == "ollama":
            # ollama gated on local_authorized instead of workspace_authorized; explicit selection required
            if not (prefer_provider == "ollama" or local_only) or not local_authorized or task not in _TABLE["optional_allowed_tasks"]:
                continue
        elif provider in _TABLE["optional"]:
            if not workspace_authorized or task not in _TABLE["optional_allowed_tasks"]:
                continue
        routes.extend(_provider_routes(provider, task, tier))
    return tuple(routes)

def pick_model(task: str, tier: str, available: set[str], workspace_authorized: bool,
               exclude_provider: str | None = None, prefer_provider: str | None = None,
               local_authorized: bool = False, local_only: bool = False) -> Route | None:
    chain = pick_model_chain(task, tier, available, workspace_authorized,
                             exclude_provider, prefer_provider, local_authorized=local_authorized,
                             local_only=local_only)
    return chain[0] if chain else None
