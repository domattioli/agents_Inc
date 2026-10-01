import os
import stat
import tempfile
import unittest
from pathlib import Path

from workerbees.keys import setup_key, available_providers

class KeysTest(unittest.TestCase):
    def setUp(self):
        self.env = Path(tempfile.mkdtemp()) / ".env"
        self.opened = []

    def test_stores_key_0600_and_never_returns_it(self):
        out = setup_key("gemini", self.env, prompt=lambda _: "SECRET123", opener=self.opened.append)
        self.assertEqual(out, "stored")
        self.assertNotIn("SECRET123", out)
        self.assertEqual(stat.S_IMODE(os.stat(self.env).st_mode), 0o600)
        self.assertIn("GEMINI_API_KEY=SECRET123", self.env.read_text())
        self.assertEqual(len(self.opened), 1)

    def test_empty_input_skips(self):
        self.assertEqual(setup_key("mistral", self.env, prompt=lambda _: "", opener=self.opened.append), "skipped")
        self.assertFalse(self.env.exists())

    def test_available_includes_required_and_stored_optional(self):
        setup_key("openrouter", self.env, prompt=lambda _: "k", opener=lambda u: None)
        self.assertEqual(available_providers(self.env, extra_env_paths=[]), {"claude", "codex", "openrouter"})

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            setup_key("aws", self.env, prompt=lambda _: "k", opener=lambda u: None)

    def test_available_scans_extra_env_paths(self):
        # Write key to main env
        setup_key("mistral", self.env, prompt=lambda _: "k1", opener=lambda u: None)
        # Write key to extra env
        extra_env = Path(tempfile.mkdtemp()) / ".env"
        setup_key("gemini", extra_env, prompt=lambda _: "k2", opener=lambda u: None)
        # Both should be in result
        result = available_providers(self.env, extra_env_paths=[extra_env])
        self.assertIn("mistral", result)
        self.assertIn("gemini", result)
        self.assertIn("claude", result)
        self.assertIn("codex", result)

    def test_available_ignores_missing_extra_path(self):
        setup_key("mistral", self.env, prompt=lambda _: "k", opener=lambda u: None)
        missing = Path(tempfile.mkdtemp()) / "nonexistent" / ".env"
        # Should not raise, just skip missing path
        result = available_providers(self.env, extra_env_paths=[missing])
        self.assertIn("mistral", result)
        self.assertIn("claude", result)


# Spec 014 (#22): OpenRouter key-name alias and key-store paths, both modules.
# Fake sentinel values in temp files only; the real .env is never opened or written.
import contextlib
import inspect
import io
from unittest import mock

import agents_inc.keys as agents_keys
import workerbees.keys as workerbees_keys

SENTINEL = "FAKE-SENTINEL-" + "q" * 24


class OpenRouterAliasAndPathsTest(unittest.TestCase):
    MODULES = (agents_keys, workerbees_keys)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _env(self, text):
        path = self.tmp / f"{len(list(self.tmp.iterdir()))}.env"
        path.write_text(text)
        return path

    def test_both_spellings_give_openrouter_in_both_modules(self):
        for mod in self.MODULES:
            for name in ("OPEN_ROUTER_API_KEY", "OPENROUTER_API_KEY"):
                with self.subTest(module=mod.__name__, name=name):
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        result = mod.available_providers(self._env(f"{name}={SENTINEL}\n"), extra_env_paths=[])
                    self.assertIn("openrouter", result)
                    self.assertNotIn("open_router", result)
                    self.assertNotIn(SENTINEL, out.getvalue() + err.getvalue() + repr(result))

    def test_default_store_is_workerbees_path_in_both_modules(self):
        for mod in self.MODULES:
            with self.subTest(module=mod.__name__):
                self.assertEqual(mod.ENV_PATH.parts[-3:], (".config", "workerbees", ".env"))
                default = inspect.signature(mod.setup_key).parameters["env_path"].default
                self.assertEqual(Path(default).parts[-3:], (".config", "workerbees", ".env"))

    def test_default_scan_reads_both_store_paths(self):
        home = self.tmp / "home"
        new = home / ".config" / "workerbees" / ".env"
        old = home / ".config" / "agents_inc" / ".env"
        for path, name in ((new, "GEMINI_API_KEY"), (old, "MISTRAL_API_KEY")):
            path.parent.mkdir(parents=True)
            path.write_text(f"{name}={SENTINEL}\n")
        for mod in self.MODULES:
            with self.subTest(module=mod.__name__):
                with mock.patch.dict(os.environ, {"HOME": str(home)}), mock.patch.object(mod, "ENV_PATH", new):
                    result = mod.available_providers(mod.ENV_PATH, extra_env_paths=[])
                self.assertIn("gemini", result)
                self.assertIn("mistral", result)

    def test_setup_key_keeps_canonical_name(self):
        for mod in self.MODULES:
            with self.subTest(module=mod.__name__):
                env = self.tmp / f"{mod.__name__}.env"
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    status = mod.setup_key("openrouter", env, prompt=lambda _: SENTINEL, opener=lambda u: None)
                self.assertEqual(status, "stored")
                self.assertTrue(env.read_text().startswith("OPENROUTER_API_KEY="))
                self.assertNotIn(SENTINEL, out.getvalue() + status)
