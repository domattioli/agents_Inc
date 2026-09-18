"""T004: tests for workerbees/config_schema.py -- stdlib dataclass validation."""
from __future__ import annotations
import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from workerbees import config_schema as cs  # noqa: E402


class TestConfigSchema(unittest.TestCase):
    def test_all_four_validate_clean(self):
        results = cs.validate_all()
        self.assertEqual(set(results.keys()), {"governance", "models", "protocols", "routing"})

    def test_malformed_governance_raises(self):
        data = json.loads((ROOT / "workerbees" / "governance.json").read_text())
        del data["agents"]
        with self.assertRaises(ValueError):
            cs.GovernanceSchema.validate(data)

    def test_malformed_models_raises(self):
        data = json.loads((ROOT / "workerbees" / "models.json").read_text())
        data["models"]["haiku"]["vendor"] = 123  # wrong type
        with self.assertRaises(ValueError):
            cs.ModelsSchema.validate(data)

    def test_malformed_protocols_raises(self):
        data = json.loads((ROOT / "workerbees" / "protocols.json").read_text())
        data["required"].append("does_not_exist_in_properties")
        with self.assertRaises(ValueError):
            cs.ProtocolsSchema.validate(data)

    def test_malformed_routing_raises(self):
        data = json.loads((ROOT / "workerbees" / "routing.json").read_text())
        del data["tiers"]["grunt"]["codex"]
        with self.assertRaises(ValueError):
            cs.RoutingSchema.validate(data)

    def test_validate_all_on_malformed_copy_raises(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            for name in ("governance", "models", "protocols", "routing"):
                (tdp / f"{name}.json").write_text(
                    (ROOT / "workerbees" / f"{name}.json").read_text()
                )
            bad = json.loads((tdp / "routing.json").read_text())
            del bad["required"]
            (tdp / "routing.json").write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                cs.validate_all(tdp)

    def test_no_third_party_dependency_added(self):
        result = subprocess.run(
            [sys.executable, "-c", "import workerbees.config_schema"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        # Parse config_schema.py and check all imports are stdlib or workerbees
        config_schema_path = ROOT / "workerbees" / "config_schema.py"
        tree = ast.parse(config_schema_path.read_text())
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]
                    if module_name not in sys.stdlib_module_names and module_name != "workerbees":
                        offenders.append(module_name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0]
                    if module_name != "__future__" and module_name not in sys.stdlib_module_names and module_name != "workerbees":
                        offenders.append(module_name)

        self.assertFalse(offenders, f"Third-party imports found: {sorted(set(offenders))}")


if __name__ == "__main__":
    unittest.main()
