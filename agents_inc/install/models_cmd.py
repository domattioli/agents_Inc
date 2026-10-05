"""D52: `agents-inc models` lists Codex pins against the local catalog; `models bump` moves one pin."""
from __future__ import annotations
import json
import sys
from pathlib import Path

from . import catalog
from .runtime import MODEL_ALIASES

AGENTS_DIR = Path(__file__).resolve().parents[1]
ROUTING = AGENTS_DIR / "routing.json"
MODELS = AGENTS_DIR / "models.json"
ORDER = ("luna", "terra", "sol", "astra")


def listing(models: list[dict] | None = None, aliases: dict[str, str] | None = None) -> list[str]:
    aliases = MODEL_ALIASES if aliases is None else aliases
    models = catalog.load() if models is None else models
    lines = []
    for alias in sorted(aliases, key=lambda a: ORDER.index(a) if a in ORDER else len(ORDER)):
        pin = aliases[alias]
        top = catalog.newest(catalog.family(pin), models)
        lines.append(f"{alias} pinned {pin} newest {top or 'unknown'} {'DRIFT' if catalog.drift(pin, models) else 'ok'}")
    return lines


def _dump(obj, indent: int = 0) -> str:
    """Match models.json formatting: objects one key per line (2 spaces), every other value inline."""
    if isinstance(obj, dict) and obj:
        pad = " " * (indent + 2)
        body = ",\n".join(f"{pad}{json.dumps(k)}: {_dump(v, indent + 2)}" for k, v in obj.items())
        return "{\n" + body + "\n" + " " * indent + "}"
    return json.dumps(obj)


def _refuse(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def bump(alias: str | None, slug: str | None, routing: Path = ROUTING, models_json: Path = MODELS,
         models: list[dict] | None = None, aliases: dict[str, str] | None = None) -> int:
    aliases = MODEL_ALIASES if aliases is None else aliases
    models = catalog.load() if models is None else models
    if alias not in aliases:
        return _refuse(f"unknown Codex alias: {alias}")
    pin = aliases[alias]
    target = slug or catalog.drift(pin, models)
    if not target:
        return _refuse(f"no newer slug than {pin} for {alias}")
    row = catalog.entry(target, models)
    if not row or row.get("visibility") != "list" or row.get("supported_in_api") is not True:
        return _refuse(f"{target} is not a listed, API-supported catalog entry")
    if target == pin:
        return _refuse(f"{alias} is already pinned to {pin}")
    if catalog.family(target) != alias:
        return _refuse(f"{target} is not in the {alias} family")
    efforts = [level["effort"] for level in row.get("supported_reasoning_levels", []) if isinstance(level, dict) and "effort" in level]
    if not efforts:
        return _refuse(f"{target} has no supported_reasoning_levels in the catalog")
    routing_text = Path(routing).read_text(encoding="utf-8")
    needle = f'"codex": "{pin}"'
    if routing_text.count(needle) != 1:
        return _refuse(f"expected exactly one {needle} in {routing}, found {routing_text.count(needle)}")
    data = json.loads(Path(models_json).read_text(encoding="utf-8"))
    table = data["models"]
    if target in table:
        table[target]["supported_efforts"] = efforts
    elif pin in table:
        new_row = dict(table[pin])
        new_row["supported_efforts"] = efforts
        rebuilt = {}
        for key, value in table.items():
            rebuilt[key] = value
            if key == pin:
                rebuilt[target] = new_row  # new entry sits right after the one it was copied from
        data["models"] = rebuilt
    else:
        return _refuse(f"models.json has no entry for {pin} to copy")
    Path(routing).write_text(routing_text.replace(needle, f'"codex": "{target}"'), encoding="utf-8")
    Path(models_json).write_text(_dump(data) + "\n", encoding="utf-8")
    print(routing)
    print(models_json)
    return 0


def run(verb: str | None, alias: str | None = None, slug: str | None = None) -> int:
    if verb == "bump":
        return bump(alias, slug)
    for line in listing():
        print(line)
    return 0
