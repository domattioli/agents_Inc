"""Smoke test for issue #35: bootstrap launcher, not-installed message, install self-check.

Every case runs with HOME pointed at a temp dir, so the real user install is never touched.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "scripts" / "agents-inc"


def _run(args, home, cwd, stdin=""):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["HOME"] = str(home)
    return subprocess.run(args, cwd=cwd, env=env, input=stdin, text=True, capture_output=True, timeout=120)


class LauncherSmokeTest(unittest.TestCase):
    def test_bootstrap_works_from_any_cwd(self):
        with tempfile.TemporaryDirectory() as raw:
            result = _run([str(LAUNCHER), "--help"], Path(raw), cwd=raw)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("doctor", result.stdout)

    def test_run_without_install_names_the_fix(self):
        with tempfile.TemporaryDirectory() as raw:
            result = _run([str(LAUNCHER), "run", "--model", "astra", "--effort", "low", "--cwd", raw], Path(raw), cwd=raw, stdin="hi")
            self.assertEqual(result.returncode, 1)
            self.assertIn("WB_NOT_INSTALLED", result.stderr)
            self.assertNotIn("Errno", result.stderr)
            doctor = _run([str(LAUNCHER), "doctor"], Path(raw), cwd=raw)
            self.assertEqual(doctor.returncode, 1)
            self.assertIn("WB_NOT_INSTALLED", doctor.stdout)

    def test_install_then_installed_launcher_is_ready(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            result = _run([str(LAUNCHER), "install", "--source", str(REPO), "--without-codex"], home, cwd=raw)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((home / ".config/agents-inc/install.json").is_file())
            installed = home / ".local/bin/agents-inc"
            self.assertTrue(installed.resolve().is_file())
            doctor = _run([str(installed), "doctor"], home, cwd=raw)
            self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
            self.assertIn("READY", doctor.stdout)


if __name__ == "__main__":
    unittest.main()
