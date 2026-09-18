import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from agents_inc.install.receipt import InstallReceipt, OwnedPath


class InstallReceiptTest(unittest.TestCase):
    def test_round_trip_is_versioned_and_has_no_sensitive_fields(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "config" / "install.json"
            receipt = InstallReceipt(
                release_hash="a" * 64,
                python_path=Path("/usr/bin/python3"),
                codex_path=Path("/opt/homebrew/bin/codex"),
                owned_paths=(OwnedPath(Path("/tmp/link"), "symlink", "/old/target"),),
            )
            receipt.save_atomic(path)
            loaded = InstallReceipt.load(path)
            self.assertEqual(loaded.schema_version, 1)
            self.assertEqual(loaded.release_hash, receipt.release_hash)
            self.assertEqual(loaded.python_path, receipt.python_path)
            self.assertEqual(loaded.codex_path, receipt.codex_path)
            self.assertEqual(loaded.owned_paths, receipt.owned_paths)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            names = set(json.loads(path.read_text()))
            self.assertFalse(names & {"token", "secret", "auth", "prompt"})

    def test_relative_owned_path_and_unsupported_schema_are_rejected(self):
        with self.assertRaises(ValueError):
            OwnedPath(Path("relative"), "file")
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "receipt.json"
            path.write_text(json.dumps({"schema_version": 2}))
            with self.assertRaises(ValueError):
                InstallReceipt.load(path)

    def test_non_object_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "receipt.json"
            path.write_text("[]")
            with self.assertRaises(ValueError):
                InstallReceipt.load(path)
