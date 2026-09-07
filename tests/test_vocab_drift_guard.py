"""Over-engineering remediation (D37): D36 found workerbees/models.json and
routing.json had silently drifted from docs/governance/ROUTING-RANKING.md's
rung table for an unknown period (opus unreachable, sol/luna cross-rung
mixed, terra missing) -- caught only by a manual audit, not by any test.
This guard makes that class of drift fail CI instead of waiting for the
next manual audit: every tier value in models.json/routing.json must be a
rung the live table of record actually names.
"""
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "skills" / "speckit-pipeline" / "scripts"))
from resolve_rung import parse_rungs_table  # noqa: E402


def _valid_rungs() -> set[str]:
    md = (REPO_ROOT / "docs" / "governance" / "ROUTING-RANKING.md").read_text()
    table = parse_rungs_table(md)
    return {k.lower() for k in table}


class VocabDriftGuardTest(unittest.TestCase):
    def test_models_json_tiers_match_canon(self):
        valid = _valid_rungs()
        models = json.loads((REPO_ROOT / "workerbees" / "models.json").read_text())["models"]
        bad = {name: m.get("tier") for name, m in models.items()
               if isinstance(m, dict) and m.get("tier") not in valid}
        self.assertEqual(bad, {}, f"models.json tier drifted from ROUTING-RANKING.md rungs {sorted(valid)}: {bad}")

    def test_routing_json_tier_keys_match_canon(self):
        valid = _valid_rungs()
        routing = json.loads((REPO_ROOT / "workerbees" / "routing.json").read_text())
        tier_keys = set(routing.get("tiers", {}))
        self.assertTrue(tier_keys <= valid, f"routing.json tiers key drifted: {tier_keys - valid}")

    def test_routing_json_task_tier_values_match_canon(self):
        valid = _valid_rungs()
        routing = json.loads((REPO_ROOT / "workerbees" / "routing.json").read_text())
        bad = {task: tier for task, tier in routing.get("task_tier", {}).items() if tier not in valid}
        self.assertEqual(bad, {}, f"routing.json task_tier drifted: {bad}")


if __name__ == "__main__":
    unittest.main()
