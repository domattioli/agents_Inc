import hashlib, json, tempfile, unittest
from pathlib import Path
from unittest import mock
from agents_inc import router

ROUTING = Path(router.__file__).parent / "routing.json"


class RouterRosterOverrideTest(unittest.TestCase):
    def _codex(self, roster_data, tier="grunt"):
        with tempfile.TemporaryDirectory() as d:
            roster = Path(d) / "roster.json"; roster.write_text(json.dumps(roster_data))
            from agents_inc.install import runtime
            real = runtime.load_model_map
            with mock.patch.object(runtime, "load_model_map", lambda *a, **k: real(roster, {})):
                return [r.model for r in router.pick_model_chain("extract", tier, {"codex"}, False)]

    def test_default_unchanged(self):
        self.assertEqual(self._codex({}), ["gpt-5.6-luna"])

    def test_roster_override_remaps_codex_slug_and_disk_untouched(self):
        before = hashlib.sha256(ROUTING.read_bytes()).hexdigest()
        target = next(m for m, p in router._CATALOG.items() if p.get("provider") == "codex" and m != "gpt-5.6-luna" and p.get("status") != "unavailable")
        self.assertEqual(self._codex({"luna": target}), [target])
        self.assertEqual(json.loads(ROUTING.read_text())["tiers"]["grunt"]["codex"], "gpt-5.6-luna")
        self.assertEqual(hashlib.sha256(ROUTING.read_bytes()).hexdigest(), before)
