from dataclasses import dataclass, field
import json
import hashlib
from typing import Dict, List, Optional
from pathlib import Path

CLEARANCE_LEVELS = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}

class RegistryError(Exception):
    pass

@dataclass(frozen=True)
class Agent:
    id: str
    name: str
    type: str
    capabilities: List[str]
    enabled: bool
    created_date: str
    clearance: str

@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    enabled: bool = True

@dataclass(frozen=True)
class Relationship:
    source_id: str
    target_id: str
    type: str

@dataclass(frozen=True)
class Registry:
    version: str
    policy_version: str
    snapshot_hash: str
    agents: Dict[str, Agent] = field(default_factory=dict)
    capabilities: Dict[str, Capability] = field(default_factory=dict)
    relationships: List[Relationship] = field(default_factory=list)

    @classmethod
    def load(cls, path: Optional[str] = None) -> "Registry":
        base = Path(path) if path else Path("workerbees")

        def read_json(filename: str):
            p = base / filename
            if not p.exists():
                raise RegistryError(f"Missing file: {filename}")
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                raise RegistryError(f"Invalid JSON in {filename}: {e}")

        gov = read_json("governance.json")
        read_json("protocols.json")
        routing = read_json("routing.json")

        hasher = hashlib.sha256()
        hasher.update((base / "governance.json").read_bytes())
        hasher.update((base / "protocols.json").read_bytes())
        hasher.update((base / "routing.json").read_bytes())
        snapshot_hash = hasher.hexdigest()

        caps: Dict[str, Capability] = {}
        for cap_name in gov.get("capabilities", []):
            if cap_name in caps:
                raise RegistryError(f"Duplicate capability id: {cap_name}")
            caps[cap_name] = Capability(id=cap_name, name=cap_name)

        agents: Dict[str, Agent] = {}
        for a_data in gov.get("agents", []):
            aid = a_data.get("id")
            if not aid:
                raise RegistryError("Agent missing id")
            if aid in agents:
                raise RegistryError(f"Duplicate agent id: {aid}")

            clearance = a_data.get("clearance", "public")
            if clearance not in CLEARANCE_LEVELS:
                raise RegistryError(f"Invalid clearance level: {clearance}")

            date_str = a_data.get("created_date", "")
            if date_str == "":
                raise RegistryError("Agent created_date must be non-empty ISO YYYY-MM-DD or null")
            if date_str is not None and len(date_str) >= 10:
                if date_str[4] != '-' or date_str[7] != '-':
                    raise RegistryError(f"Invalid date format: {date_str}")
                try:
                    parts = [int(p) for p in date_str.split('-')]
                    if len(parts) < 3:
                        raise ValueError()
                except ValueError:
                    raise RegistryError(f"Invalid date values: {date_str}")

            agent_caps = a_data.get("capabilities", [])
            for cap_id in agent_caps:
                if cap_id not in caps:
                    raise RegistryError(f"Agent {aid} refs missing cap {cap_id}")

            agents[aid] = Agent(
                id=aid,
                name=a_data.get("name", ""),
                type=a_data.get("type", ""),
                capabilities=agent_caps,
                enabled=bool(a_data.get("enabled", True)),
                created_date=date_str,
                clearance=clearance
            )

        relationships: List[Relationship] = []
        for r_data in gov.get("relationships", []):
            src = r_data.get("source_agent_id")
            dst = r_data.get("target_agent_id")
            rel_type = r_data.get("relationship_type")
            if not src or not dst or not rel_type:
                raise RegistryError("Relationship missing source/target/type")
            if src not in agents:
                raise RegistryError(f"Relationship refs missing source: {src}")
            if dst not in agents:
                raise RegistryError(f"Relationship refs missing target: {dst}")

            relationships.append(Relationship(source_id=src, target_id=dst, type=rel_type))

        return cls(
            version=gov.get("version", "1.0"),
            policy_version=gov.get("policy_version", "1.0"),
            snapshot_hash=snapshot_hash,
            agents=agents,
            capabilities=caps,
            relationships=relationships
        )

    def edge(self, src: str, dst: str, rel_type: str) -> Optional[Relationship]:
        for r in self.relationships:
            if r.source_id == src and r.target_id == dst and r.type == rel_type:
                return r
        return None

    def agent(self, id: str, include_disabled: bool = False) -> Optional[Agent]:
        a = self.agents.get(id)
        if a is None:
            return None
        return a if include_disabled or a.enabled else None

    def capability(self, id: str, include_disabled: bool = False) -> Optional[Capability]:
        c = self.capabilities.get(id)
        if c is None:
            return None
        return c if include_disabled or c.enabled else None
