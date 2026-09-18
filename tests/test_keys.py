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
        self.assertEqual(available_providers(self.env), {"claude", "codex", "openrouter"})

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
