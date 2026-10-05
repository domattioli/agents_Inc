import json
import subprocess
import unittest
from pathlib import Path

from agents_inc.install.runtime import MODEL_ALIASES

ROOT = Path(__file__).resolve().parents[1]
AT_ROUTE = ROOT / "skills/codex-bridge/scripts/at_route.sh"
ALIASES = ("astra", "sol", "terra", "luna")


class ModelSourcesAgreeTest(unittest.TestCase):
    def setUp(self):
        self.routing = json.loads((ROOT / "agents_inc/routing.json").read_text())
        self.pins = {slug.rsplit("-", 1)[-1]: slug for slug in (t["codex"] for t in self.routing["tiers"].values())}

    def test_routing_covers_aliases(self):
        self.assertEqual(set(self.pins), set(ALIASES))

    def test_runtime_matches_routing(self):
        self.assertEqual(MODEL_ALIASES, self.pins)

    def test_at_route_resolve_matches_routing(self):
        for alias in ALIASES:
            done = subprocess.run(["bash", str(AT_ROUTE), "--resolve", alias], capture_output=True, text=True, check=False)
            self.assertEqual((done.returncode, done.stdout.strip()), (0, self.pins[alias]), alias)

    def test_at_route_resolve_unknown_alias(self):
        done = subprocess.run(["bash", str(AT_ROUTE), "--resolve", "nova"], capture_output=True, text=True, check=False)
        self.assertEqual((done.returncode, done.stdout), (1, ""))

    def test_pinned_slugs_have_models_entry_with_efforts(self):
        models = json.loads((ROOT / "agents_inc/models.json").read_text())["models"]
        for slug in self.pins.values():
            self.assertTrue(models.get(slug, {}).get("supported_efforts"), slug)


if __name__ == "__main__":
    unittest.main()
