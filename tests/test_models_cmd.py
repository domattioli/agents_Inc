import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from agents_inc.install import catalog, models_cmd

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures/catalog/models_cache.json"


class ModelsCmdTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.routing = self.dir / "routing.json"
        self.models_json = self.dir / "models.json"
        self.routing.write_text((ROOT / "agents_inc/routing.json").read_text())
        self.models_json.write_text((ROOT / "agents_inc/models.json").read_text())
        self.catalog = catalog.load(FIXTURE)

    def tearDown(self): self.tmp.cleanup()

    def _bump(self, alias, slug=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = models_cmd.bump(alias, slug, self.routing, self.models_json, self.catalog)
        return code, out.getvalue(), err.getvalue()

    def test_listing_format_and_order(self):
        lines = models_cmd.listing(self.catalog)
        self.assertEqual(len(lines), 4)
        self.assertEqual([line.split()[0] for line in lines], ["luna", "terra", "sol", "astra"])
        self.assertEqual(lines[2], "sol pinned gpt-5.6-sol newest gpt-6.1-sol DRIFT")
        self.assertEqual(lines[1], "terra pinned gpt-5.6-terra newest gpt-5.6-terra ok")
        self.assertTrue(lines[0].endswith("DRIFT"))

    def test_listing_without_cache_says_unknown(self):
        self.assertEqual(models_cmd.listing([])[2], "sol pinned gpt-5.6-sol newest unknown ok")

    def test_bump_default_target(self):
        code, out, _ = self._bump("sol")
        self.assertEqual(code, 0)
        self.assertEqual(out.split(), [str(self.routing), str(self.models_json)])
        before = (ROOT / "agents_inc/routing.json").read_text()
        self.assertEqual(self.routing.read_text(), before.replace('"codex": "gpt-5.6-sol"', '"codex": "gpt-6.1-sol"'))
        table = json.loads(self.models_json.read_text())["models"]
        old = json.loads((ROOT / "agents_inc/models.json").read_text())["models"]["gpt-5.6-sol"]
        self.assertEqual(table["gpt-6.1-sol"]["supported_efforts"], ["low", "medium", "high", "xhigh", "max"])
        self.assertEqual({k: v for k, v in table["gpt-6.1-sol"].items() if k != "supported_efforts"},
                         {k: v for k, v in old.items() if k != "supported_efforts"})
        self.assertEqual(table["gpt-5.6-sol"], old)
        keys = list(table)
        self.assertEqual(keys.index("gpt-6.1-sol"), keys.index("gpt-5.6-sol") + 1)

    def test_bump_explicit_slug(self):
        code, _, _ = self._bump("sol", "gpt-6-sol")
        self.assertEqual(code, 0)
        self.assertIn('"codex": "gpt-6-sol"', self.routing.read_text())
        self.assertEqual(json.loads(self.models_json.read_text())["models"]["gpt-6-sol"]["supported_efforts"], ["low", "medium"])

    def test_models_json_formatting_survives_noop_dump(self):
        text = self.models_json.read_text()
        self.assertEqual(models_cmd._dump(json.loads(text)) + "\n", text)

    def test_refusals_exit_2_and_write_nothing(self):
        routing, models = self.routing.read_text(), self.models_json.read_text()
        cases = [("sol", "gpt-0-sol"), ("sol", "gpt-5.6-sol"), ("nova", None), ("terra", None), ("astra", "gpt-7-astra"),
                 ("terra", "gpt-9-terra"), ("sol", "gpt-6-astra")]
        for alias, slug in cases:
            code, _, err = self._bump(alias, slug)
            self.assertEqual(code, 2, (alias, slug))
            self.assertTrue(err.strip())
        self.assertEqual(self.routing.read_text(), routing)
        self.assertEqual(self.models_json.read_text(), models)

    def test_ambiguous_routing_occurrence_refused(self):
        self.routing.write_text(self.routing.read_text() + '\n"codex": "gpt-5.6-sol"\n')
        self.assertEqual(self._bump("sol")[0], 2)


if __name__ == "__main__":
    unittest.main()
