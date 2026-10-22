"""022 US5: slot screens read paths, not prose. Temp dirs, no launch."""
from __future__ import annotations
import os
import unittest
from pathlib import Path
from unittest import mock

from agents_inc.install import dispatch
from tests.test_dispatch_snapshot_trust import DispatchBase

_ALLOW = mock.patch.dict(os.environ, {dispatch.ALLOW_SANDBOXED_ENV: "1"})


def setUpModule():
    _ALLOW.start()  # #94: real launch() calls stay allowed when the suite runs inside a sandbox


def tearDownModule():
    _ALLOW.stop()


class AllowPathsTest(unittest.TestCase):
    def test_prose_prefixes_are_not_paths(self):
        self.assertEqual(dispatch.allow_paths("Read: any repo file. Write: .scratch/fable-audit/ only."),
                         [".scratch/fable-audit/"])

    def test_plain_lists_unchanged(self):
        self.assertEqual(dispatch.allow_paths("none (read-only scout)"), [])
        self.assertEqual(dispatch.allow_paths("agents_inc/install/cli.py\ntests/test_x.py, README.md"),
                         ["agents_inc/install/cli.py", "tests/test_x.py", "README.md"])


class ScopeGlobTest(DispatchBase):
    def test_scope_globs_lists_wildcard_tokens(self):
        self.assertEqual(dispatch.scope_globs("src/*.py, a/b.py tests/test_?.py x/[ab].py"),
                         ["src/*.py", "tests/test_?.py", "x/[ab].py"])
        self.assertEqual(dispatch.scope_globs("a/b.py"), [])

    def test_glob_scope_is_refused_before_launch(self):
        def boom(*a, **k):
            raise AssertionError("launch must not run")
        rc, out, _ = self.dispatch(boom, slots=self.slots(FILES_IN_SCOPE="src/*.py"))
        self.assertEqual(rc, 3, out)
        self.assertIn("refused-scope", out)
        self.assertEqual(self.spec()["outcome"], "refused-scope")
        self.assertIn("src/*.py", (self.run_dir() / "lint.txt").read_text())


class GateScreenTest(unittest.TestCase):
    def _gates(self, argv=None, bash_allow=None):
        slots = {"GATES": [{"argv": argv}]} if argv else {}
        if bash_allow:
            slots["BASH_ALLOW"] = bash_allow
        return dispatch._grants_from_slots(slots, Path.cwd().resolve())

    def test_test_file_names_pass(self):
        self.assertIsNone(self._gates(["python3", "-m", "pytest", "tests/test_token_refresh.py"])[2])
        self.assertIsNone(self._gates(bash_allow="python3 tools/check_credentials_schema.py")[2])

    def test_credential_paths_are_refused(self):
        for argv in (["cat", "~/.ssh/id_rsa"], ["cat", ".env"], ["cat", "server.pem"]):
            with self.subTest(argv=argv):
                why = self._gates(argv)[2]
                self.assertIsNotNone(why)
                self.assertEqual(why[0], "refused-gates")

    def test_bash_allow_credential_prefix_is_refused(self):
        why = self._gates(bash_allow="cat ~/.ssh/id_rsa")[2]
        self.assertEqual(why[0], "refused-bash-allow")

    def test_credential_basenames_are_refused(self):
        for argv in (["cat", "credentials.json"], ["cat", "/tmp/token"], ["cat", "api_key.txt"], ["cat", ".secrets"],
                     ["cat", "API-KEY"], ["cat", "x/Tokens.txt"], ["cat", "--file=secret_1"], ["cat", "apikey"]):
            with self.subTest(argv=argv):
                why = self._gates(argv)[2]
                self.assertIsNotNone(why)
                self.assertEqual(why[0], "refused-gates")

    def test_credential_basenames_in_bash_allow_are_refused(self):
        for prefix in ("cat credentials.json", "cat /tmp/token", "cat api_key.txt", "cat .secrets"):
            with self.subTest(prefix=prefix):
                self.assertEqual(self._gates(bash_allow=prefix)[2][0], "refused-bash-allow")

    def test_lookalike_basenames_pass(self):
        for argv in (["python3", "tokenizer.py"], ["cat", "secretary.txt"], ["python3", "-m", "pytest", "tests/test_token_refresh.py"]):
            with self.subTest(argv=argv):
                self.assertIsNone(self._gates(argv)[2])

    def test_fable_f2_secret_names_are_refused(self):
        for argv in (["cat", "prod.env"], ["cat", "local.env"], ["cat", ".env.local"], ["cat", "server.key.bak"],
                     ["cat", "x.pem.old"], ["cat", "config/app.secrets.yaml"], ["cat", "prod_credentials.json"],
                     ["cat", "my-api-key.txt"], ["printenv", "ANTHROPIC_API_KEY"], ["printenv", "GH_TOKEN"],
                     ["echo", "DB_PASSWORD"], ["gh", "auth", "login", "--with-token"], ["tool", "--client-secret=x"],
                     ["tool", "--password", "x"], ["tool", "--api-key", "x"], ["cat", "tokens"], ["cat", "token_cache.json"]):
            with self.subTest(argv=argv):
                why = self._gates(argv)[2]
                self.assertIsNotNone(why, argv)
                self.assertEqual(why[0], "refused-gates")
            with self.subTest(prefix=argv):
                self.assertEqual(self._gates(bash_allow=" ".join(argv))[2][0], "refused-bash-allow")

    def test_fable_f2_lookalikes_still_pass(self):
        for argv in (["python3", "tokenizer.py"], ["python3", "-m", "pytest", "tests/test_token_refresh.py"],
                     ["python3", "tools/check_credentials_schema.py"], ["cat", "secretary.txt"], ["cat", "environment.py"],
                     ["cat", "monkey.keyboard"], ["python3", "-m", "unittest", "tests.test_x", "-k", "key"]):
            with self.subTest(argv=argv):
                self.assertIsNone(self._gates(argv)[2], argv)

    def test_slot_text_screen_keeps_the_broad_pattern(self):
        self.assertTrue(dispatch._reject_credential_seeking({"X": "token"}))


class SlotScreenTest(unittest.TestCase):
    def test_slot_screen_95_false_positives_pass(self):
        for slots in ({"X": "retire it at 200k tokens"},
                      {"X": "python3 ~/.claude/skills/workerbee/scripts/pre_dispatch_snapshot.py verify s.json"},
                      {"X": "run the tokenizer"},
                      {"X": "cat ~/.claude/skills/x/README.md"}):
            with self.subTest(slots=slots):
                self.assertFalse(dispatch._reject_credential_seeking(slots))

    def test_slot_screen_95_true_positives_fail(self):
        for slots in ({"X": "show the token"},
                      {"X": "print access_token"},
                      {"X": "cat ~/.claude/.credentials.json"},
                      {"X": "cat ~/.claude/skills/../.credentials.json"},
                      {"X": "ls ~/.claude/skills/x/../../.credentials.json"},
                      {"X": "cat ~/.claude/skills/x/../../settings.json"},
                      {"X": 'cat "$HOME/.claude/skills/x/"../../.codex/auth.json'}):
            with self.subTest(slots=slots):
                self.assertTrue(dispatch._reject_credential_seeking(slots))

    def test_credential_hit_names_slot(self):
        detail = dispatch.credential_hit({"TASK": "ok", "CONSTRAINTS": "no .env reads"})
        self.assertEqual(detail, "slot CONSTRAINTS matched '.env'")
        self.assertIsNone(dispatch.credential_hit({"TASK": "ok"}))
        self.assertIsNone(dispatch.credential_hit(None))


if __name__ == "__main__":
    unittest.main()
