import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agents_inc.install.cli import install_convenience_launcher, uninstall
from agents_inc.install.receipt import InstallReceipt, OwnedPath
from agents_inc.install.paths import InstallPaths


class CliTest(unittest.TestCase):
    def test_help_lists_lifecycle_commands(self):
        result = subprocess.run([sys.executable, "-m", "agents_inc.install.cli", "--help"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        for command in ("install", "run", "doctor", "repair", "rollback", "uninstall"):
            self.assertIn(command, result.stdout)

    def test_install_refuses_to_overwrite_foreign_convenience_launcher(self):
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "source"; (source / "agents_inc").mkdir(parents=True)
            (source / "agents_inc" / "models.json").write_text("{}")
            for name in ("workerbee", "codex-bridge"):
                (source / "skills" / name).mkdir(parents=True); (source / "skills" / name / "SKILL.md").write_text("x")
            paths = InstallPaths.for_home(Path(raw) / "home"); paths.launcher.parent.mkdir(parents=True)
            paths.launcher.write_text("foreign")
            with self.assertRaisesRegex(RuntimeError, "WB_CONFIG_CONFLICT"):
                install_convenience_launcher(paths)

    def test_uninstall_preserves_replaced_launcher_and_receipt(self):
        with tempfile.TemporaryDirectory() as raw:
            paths = InstallPaths.for_home(Path(raw) / "home")
            paths.launcher.parent.mkdir(parents=True); paths.launcher.symlink_to("/replacement")
            receipt = InstallReceipt("a" * 64, Path("/usr/bin/python3"), Path("/usr/bin/codex"), (OwnedPath(paths.launcher, "symlink"),))
            receipt.save_atomic(paths.receipt)
            retained = uninstall(paths, receipt)
            self.assertEqual(paths.launcher.readlink(), Path("/replacement"))
            self.assertTrue(paths.receipt.exists())
            self.assertIn(paths.launcher, retained)
