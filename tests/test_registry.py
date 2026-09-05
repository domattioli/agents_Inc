import unittest
import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from workerbees.registry import Registry, RegistryError, Agent, Capability, Relationship

class TestRegistry(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.base = Path(self.temp_dir)

        gov = {
            "version": "2026-09-05.1",
            "policy_version": "2026-09-05.1",
            "capabilities": ["extract.markdown", "draft.brief", "review.claims"],
            "agents": [
                {
                    "id": "agent-1",
                    "name": "Supervisor",
                    "type": "supervisor",
                    "capabilities": ["extract.markdown", "draft.brief"],
                    "enabled": True,
                    "created_date": "2026-01-15",
                    "clearance": "confidential"
                },
                {
                    "id": "agent-2",
                    "name": "Worker",
                    "type": "worker",
                    "capabilities": ["extract.markdown"],
                    "enabled": True,
                    "created_date": "2026-01-15",
                    "clearance": "internal"
                }
            ],
            "relationships": [
                {
                    "source_agent_id": "agent-1",
                    "target_agent_id": "agent-2",
                    "relationship_type": "delegates_to",
                    "relationship_params": ["extract"]
                }
            ]
        }

        proto = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "WorkerBeesEnvelopeV1",
            "type": "object"
        }

        routing = {
            "required": ["claude"],
            "optional": [],
            "tiers": {
                "cheap": {"claude": "haiku"},
                "mid": {"claude": "sonnet"},
                "frontier": {"claude": "fable"}
            },
            "task_tier": {"extract": "cheap"},
            "optional_allowed_tasks": []
        }

        (self.base / "governance.json").write_text(json.dumps(gov))
        (self.base / "protocols.json").write_text(json.dumps(proto))
        (self.base / "routing.json").write_text(json.dumps(routing))

    def test_load_ok(self):
        reg = Registry.load(str(self.base))
        self.assertEqual(reg.version, "2026-09-05.1")
        self.assertEqual(len(reg.agents), 2)
        self.assertEqual(len(reg.capabilities), 3)
        self.assertEqual(len(reg.relationships), 1)

    def test_duplicate_agent_id_raises(self):
        gov = json.loads((self.base / "governance.json").read_text())
        gov["agents"].append({
            "id": "agent-1",  # duplicate
            "name": "Dup",
            "type": "worker",
            "capabilities": [],
            "enabled": True,
            "created_date": "2026-01-15",
            "clearance": "public"
        })
        (self.base / "governance.json").write_text(json.dumps(gov))

        with self.assertRaises(RegistryError) as ctx:
            Registry.load(str(self.base))
        self.assertIn("Duplicate agent id", str(ctx.exception))

    def test_missing_capability_ref_raises(self):
        gov = json.loads((self.base / "governance.json").read_text())
        gov["agents"][0]["capabilities"].append("nonexistent.capability")
        (self.base / "governance.json").write_text(json.dumps(gov))

        with self.assertRaises(RegistryError) as ctx:
            Registry.load(str(self.base))
        self.assertIn("missing cap", str(ctx.exception))

    def test_missing_agent_ref_in_relationship_raises(self):
        gov = json.loads((self.base / "governance.json").read_text())
        gov["relationships"][0]["target_agent_id"] = "nonexistent-agent"
        (self.base / "governance.json").write_text(json.dumps(gov))

        with self.assertRaises(RegistryError) as ctx:
            Registry.load(str(self.base))
        self.assertIn("missing target", str(ctx.exception))

    def test_snapshot_hash_64_hex(self):
        reg = Registry.load(str(self.base))
        self.assertEqual(len(reg.snapshot_hash), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in reg.snapshot_hash))

    def test_unknown_agent_returns_none(self):
        reg = Registry.load(str(self.base))
        result = reg.agent("nonexistent-agent")
        self.assertIsNone(result)

    def test_unknown_capability_returns_none(self):
        reg = Registry.load(str(self.base))
        result = reg.capability("nonexistent.capability")
        self.assertIsNone(result)

    def test_edge_found(self):
        reg = Registry.load(str(self.base))
        edge = reg.edge("agent-1", "agent-2", "delegates_to")
        self.assertIsNotNone(edge)
        self.assertEqual(edge.type, "delegates_to")

    def test_edge_not_found(self):
        reg = Registry.load(str(self.base))
        edge = reg.edge("agent-2", "agent-1", "delegates_to")
        self.assertIsNone(edge)

    def test_invalid_clearance_raises(self):
        gov = json.loads((self.base / "governance.json").read_text())
        gov["agents"][0]["clearance"] = "invalid_level"
        (self.base / "governance.json").write_text(json.dumps(gov))

        with self.assertRaises(RegistryError) as ctx:
            Registry.load(str(self.base))
        self.assertIn("Invalid clearance", str(ctx.exception))

    def test_disabled_agent_returns_none_by_default(self):
        gov = json.loads((self.base / "governance.json").read_text())
        gov["agents"].append({
            "id": "agent-disabled",
            "name": "Disabled Agent",
            "type": "worker",
            "capabilities": [],
            "enabled": False,
            "created_date": "2026-01-15",
            "clearance": "public"
        })
        (self.base / "governance.json").write_text(json.dumps(gov))
        reg = Registry.load(str(self.base))

        result = reg.agent("agent-disabled")
        self.assertIsNone(result)

        result_with_disabled = reg.agent("agent-disabled", include_disabled=True)
        self.assertIsNotNone(result_with_disabled)
        self.assertEqual(result_with_disabled.id, "agent-disabled")

    def test_disabled_capability_returns_none_by_default(self):
        gov = json.loads((self.base / "governance.json").read_text())
        gov["capabilities"].append("disabled.capability")
        gov["agents"][0]["capabilities"].append("disabled.capability")
        (self.base / "governance.json").write_text(json.dumps(gov))
        reg = Registry.load(str(self.base))

        disabled_cap = Capability(id="disabled.capability", name="Disabled Cap", enabled=False)
        caps_dict = dict(reg.capabilities)
        caps_dict["disabled.capability"] = disabled_cap
        reg = Registry(
            version=reg.version,
            policy_version=reg.policy_version,
            snapshot_hash=reg.snapshot_hash,
            agents=reg.agents,
            capabilities=caps_dict,
            relationships=reg.relationships
        )

        result = reg.capability("disabled.capability")
        self.assertIsNone(result)

        result_with_disabled = reg.capability("disabled.capability", include_disabled=True)
        self.assertIsNotNone(result_with_disabled)

    def test_empty_created_date_raises_error(self):
        gov = json.loads((self.base / "governance.json").read_text())
        gov["agents"][0]["created_date"] = ""
        (self.base / "governance.json").write_text(json.dumps(gov))

        with self.assertRaises(RegistryError) as ctx:
            Registry.load(str(self.base))
        self.assertIn("must be non-empty ISO YYYY-MM-DD", str(ctx.exception))

    def test_provider_for_returns_runtime(self):
        """provider_for returns agent.runtime if present."""
        gov = json.loads((self.base / "governance.json").read_text())
        gov["agents"][0]["runtime"] = "claude"
        (self.base / "governance.json").write_text(json.dumps(gov))
        reg = Registry.load(str(self.base))

        result = reg.provider_for("agent-1")
        self.assertEqual(result, "claude")

    def test_provider_for_returns_endpoint(self):
        """provider_for returns agent.endpoint if runtime not present."""
        gov = json.loads((self.base / "governance.json").read_text())
        gov["agents"][0]["endpoint"] = "codex"
        (self.base / "governance.json").write_text(json.dumps(gov))
        reg = Registry.load(str(self.base))

        result = reg.provider_for("agent-1")
        self.assertEqual(result, "codex")

    def test_provider_for_returns_none_if_agent_not_found(self):
        """provider_for returns None if agent_id not found."""
        reg = Registry.load(str(self.base))
        result = reg.provider_for("nonexistent-agent")
        self.assertIsNone(result)

    def test_provider_for_returns_none_if_no_runtime_or_endpoint(self):
        """provider_for returns None if agent has no runtime/endpoint."""
        reg = Registry.load(str(self.base))
        result = reg.provider_for("agent-1")
        self.assertIsNone(result)

    def test_provider_for_case_insensitive(self):
        """provider_for normalizes provider name to lowercase."""
        gov = json.loads((self.base / "governance.json").read_text())
        gov["agents"][0]["runtime"] = "CLAUDE"
        (self.base / "governance.json").write_text(json.dumps(gov))
        reg = Registry.load(str(self.base))

        result = reg.provider_for("agent-1")
        self.assertEqual(result, "claude")

    def test_provider_for_filters_unknown_providers(self):
        """provider_for returns None if runtime/endpoint is unknown provider."""
        gov = json.loads((self.base / "governance.json").read_text())
        gov["agents"][0]["runtime"] = "unknown_provider"
        (self.base / "governance.json").write_text(json.dumps(gov))
        reg = Registry.load(str(self.base))

        result = reg.provider_for("agent-1")
        self.assertIsNone(result)

if __name__ == "__main__":
    unittest.main()
