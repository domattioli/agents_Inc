"""T004: stdlib-only schema hardening for workerbees/{governance,models,protocols,routing}.json.

No third-party deps -- dataclasses + json + pathlib only. Raises ValueError with a
descriptive message on any malformed file.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def _load(name: str) -> Any:
    return json.loads((ROOT / name).read_text())


def _require(d: dict, key: str, typ: type | tuple[type, ...], where: str) -> Any:
    if key not in d:
        raise ValueError(f"{where}: missing required key {key!r}")
    val = d[key]
    if not isinstance(val, typ):
        raise ValueError(f"{where}: key {key!r} expected {typ}, got {type(val)}")
    return val


@dataclass(frozen=True)
class GovernanceSchema:
    version: str
    policy_version: str
    trust_hierarchy: list
    capabilities: list
    agents: list

    @classmethod
    def validate(cls, data: dict) -> "GovernanceSchema":
        where = "governance.json"
        version = _require(data, "version", str, where)
        policy_version = _require(data, "policy_version", str, where)
        trust_hierarchy = _require(data, "trust_hierarchy", list, where)
        capabilities = _require(data, "capabilities", list, where)
        agents = _require(data, "agents", list, where)
        for i, agent in enumerate(agents):
            if not isinstance(agent, dict):
                raise ValueError(f"{where}: agents[{i}] must be an object")
            _require(agent, "id", str, f"{where}.agents[{i}]")
            _require(agent, "name", str, f"{where}.agents[{i}]")
            _require(agent, "type", str, f"{where}.agents[{i}]")
            _require(agent, "capabilities", list, f"{where}.agents[{i}]")
        return cls(version, policy_version, trust_hierarchy, capabilities, agents)


@dataclass(frozen=True)
class ModelsSchema:
    version: str
    models: dict

    @classmethod
    def validate(cls, data: dict) -> "ModelsSchema":
        where = "models.json"
        version = _require(data, "version", str, where)
        models = _require(data, "models", dict, where)
        for name, spec in models.items():
            mwhere = f"{where}.models[{name!r}]"
            if not isinstance(spec, dict):
                raise ValueError(f"{mwhere}: must be an object")
            _require(spec, "vendor", (str, type(None)), mwhere)
            _require(spec, "provider", str, mwhere)
            _require(spec, "tier", str, mwhere)
            _require(spec, "tasks_good", list, mwhere)
            _require(spec, "tasks_bad", list, mwhere)
            _require(spec, "status", str, mwhere)
        return cls(version, models)


@dataclass(frozen=True)
class ProtocolsSchema:
    schema_id: str
    title: str
    type_: str
    required: list
    properties: dict

    @classmethod
    def validate(cls, data: dict) -> "ProtocolsSchema":
        where = "protocols.json"
        schema_id = _require(data, "$schema", str, where)
        title = _require(data, "title", str, where)
        type_ = _require(data, "type", str, where)
        required = _require(data, "required", list, where)
        properties = _require(data, "properties", dict, where)
        for key in required:
            if key not in properties:
                raise ValueError(f"{where}: required key {key!r} not in properties")
        return cls(schema_id, title, type_, required, properties)


@dataclass(frozen=True)
class RoutingSchema:
    required: list
    optional: list
    tiers: dict
    task_tier: dict

    @classmethod
    def validate(cls, data: dict) -> "RoutingSchema":
        where = "routing.json"
        required = _require(data, "required", list, where)
        optional = _require(data, "optional", list, where)
        tiers = _require(data, "tiers", dict, where)
        task_tier = _require(data, "task_tier", dict, where)
        for tier_name, tier_spec in tiers.items():
            if not isinstance(tier_spec, dict):
                raise ValueError(f"{where}.tiers[{tier_name!r}]: must be an object")
            for req in required:
                if req not in tier_spec:
                    raise ValueError(
                        f"{where}.tiers[{tier_name!r}]: missing required vendor {req!r}"
                    )
        return cls(required, optional, tiers, task_tier)


def validate_all(root: Path | None = None) -> dict[str, Any]:
    """Validate all 4 config files. Raises ValueError on the first malformed file."""
    base = root or ROOT
    results = {}
    results["governance"] = GovernanceSchema.validate(
        json.loads((base / "governance.json").read_text())
    )
    results["models"] = ModelsSchema.validate(json.loads((base / "models.json").read_text()))
    results["protocols"] = ProtocolsSchema.validate(
        json.loads((base / "protocols.json").read_text())
    )
    results["routing"] = RoutingSchema.validate(json.loads((base / "routing.json").read_text()))
    return results


if __name__ == "__main__":
    validate_all()
    print("all 4 config files valid")
