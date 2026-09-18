import io
import os
import stat
import tempfile
import unittest
from pathlib import Path
import json

from agents_inc.install.receipt import InstallReceipt
from agents_inc.install.runtime import MODEL_ALIASES, build_codex_argv, resolve_executable, run_codex


class RuntimeTest(unittest.TestCase):
    def test_aliases_and_isolated_argv(self):
        self.assertEqual(MODEL_ALIASES, {"astra": "gpt-6-astra", "sol": "gpt-5.6-sol", "terra": "gpt-5.6-terra", "luna": "gpt-5.6-luna"})
        argv = build_codex_argv(Path("/opt/Codex CLI/codex"), "astra", "medium", Path("/work here"), {"gpt-6-astra": ["medium"]})
        self.assertEqual(argv[:4], ["/opt/Codex CLI/codex", "exec", "-m", "gpt-6-astra"])
        self.assertIn("read-only", argv)
        self.assertIn('shell_environment_policy.inherit="none"', argv)
        self.assertIn('web_search="disabled"', argv)
        self.assertIn("features.shell_tool=false", argv)
        self.assertEqual(argv[-1], "-")

    def test_resolution_needs_absolute_executable(self):
        with tempfile.TemporaryDirectory() as raw:
            exe = Path(raw) / "bin" / "codex"
            exe.parent.mkdir(); exe.write_text("#!/bin/sh\n")
            exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
            self.assertEqual(resolve_executable("codex", str(exe.parent)), exe.resolve())
        with self.assertRaises(FileNotFoundError):
            resolve_executable("codex", "")

    def test_unsupported_effort_fails_before_execution(self):
        with self.assertRaises(ValueError):
            build_codex_argv(Path("/x/codex"), "luna", "ultra", Path("/tmp"), {"gpt-5.6-luna": ["low"]})

    def test_bundled_catalog_declares_supported_efforts_for_every_alias(self):
        models = json.loads((Path(__file__).parents[1] / "agents_inc/models.json").read_text())["models"]
        for slug in MODEL_ALIASES.values():
            self.assertIn("supported_efforts", models[slug])
            self.assertIn("medium", models[slug]["supported_efforts"])
