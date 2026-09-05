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

if __name__ == "__main__":
    unittest.main()
