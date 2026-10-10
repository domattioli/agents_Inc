"""`agents-inc models chain`: list, set and clear the default REPORTING CHAIN seats. Temp settings only."""
from __future__ import annotations
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents_inc import model_sync
from agents_inc.install import cli, models_cmd


class ModelsChainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Path(self.tmp.name) / ".config" / "agents-inc" / "settings.json"
        self.patch = mock.patch.object(model_sync, "DEFAULT_SETTINGS", str(self.settings))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def _cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(["models", *argv])
        return rc, out.getvalue(), err.getvalue()

    def test_list_defaults_to_ladder(self):
        rc, out, _ = self._cli("chain")
        self.assertEqual(rc, 0)
        self.assertIn("claude ladder haiku < sonnet < opus < fable", out)
        self.assertIn("codex ladder luna < terra < sol < astra", out)
        self.assertIn("supervisor ladder ladder", out)
        self.assertFalse(self.settings.exists())

    def test_set_writes_chain_and_keeps_other_keys(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps({"model_updates": "auto"}))
        rc, _, _ = self._cli("chain", "supervisor=opus", "executive=fable")
        self.assertEqual(rc, 0)
        data = json.loads(self.settings.read_text())
        self.assertEqual(data, {"model_updates": "auto", "chain": {"supervisor": "opus", "executive": "fable"}})
        rc, out, _ = self._cli("chain")
        self.assertIn("supervisor opus setting", out)
        self.assertIn("executive fable setting", out)

    def test_clear_removes_chain(self):
        self._cli("chain", "supervisor=opus")
        rc, _, _ = self._cli("chain", "--clear")
        self.assertEqual(rc, 0)
        self.assertNotIn("chain", json.loads(self.settings.read_text()))

    def test_unknown_alias_rejected_file_untouched(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('{"a": 1}')
        before = self.settings.read_text()
        rc, _, err = self._cli("chain", "supervisor=gpt9")
        self.assertEqual(rc, 2)
        self.assertIn("unknown chain value", err)
        self.assertEqual(self.settings.read_text(), before)

    def test_bad_key_rejected(self):
        rc, _, _ = self._cli("chain", "delegate=opus")
        self.assertEqual(rc, 2)

    def test_role_words_accepted(self):
        self.assertEqual(models_cmd.chain(["supervisor=CoS"], settings=self.settings), 0)
        self.assertEqual(json.loads(self.settings.read_text())["chain"], {"supervisor": "CoS"})

    def test_bump_still_routes(self):
        with mock.patch.object(models_cmd, "bump", return_value=0) as bump:
            self.assertEqual(models_cmd.run("bump", "sol", None), 0)
        bump.assert_called_once()


if __name__ == "__main__":
    unittest.main()
