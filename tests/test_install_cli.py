import os
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


class RunGuardTest(unittest.TestCase):
    def test_run_rejects_claude_alias_and_passes_codex_alias(self):
        import contextlib, io
        from unittest import mock
        from agents_inc.install import cli
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            paths = InstallPaths.for_home(tmp / "home")
            rel = paths.releases / "h"; rel.mkdir(parents=True)
            paths.current.parent.mkdir(parents=True, exist_ok=True); paths.current.symlink_to(rel)
            InstallReceipt("a" * 64, Path("/usr/bin/python3"), None).save_atomic(paths.receipt)
            with mock.patch.object(cli, "_paths", return_value=paths), mock.patch.object(cli, "_efforts", return_value={}), \
                 mock.patch.object(cli, "run_codex", return_value=0) as rc:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    code = cli.main(["run", "--model", "opus", "--effort", "low", "--cwd", str(tmp)])
                self.assertEqual(code, 2)
                self.assertIn(f"Claude aliases go through: agents-inc dispatch --model opus --effort low --cwd {tmp}", err.getvalue())
                rc.assert_not_called()
                self.assertEqual(cli.main(["run", "--model", "luna", "--cwd", str(tmp)]), 0)
                rc.assert_called_once()


class RepairTest(unittest.TestCase):
    def test_install_and_repair_record_stable_codex_not_shim(self):
        import argparse
        from agents_inc.install import cli
        from unittest import mock
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = tmp / "source"; (source / "agents_inc").mkdir(parents=True)
            (source / "agents_inc" / "models.json").write_text("{}")
            for name in ("workerbee", "codex-bridge"):
                (source / "skills" / name).mkdir(parents=True); (source / "skills" / name / "SKILL.md").write_text("x")
            for d in ("x-shims/abc", "real"):
                (tmp / d).mkdir(parents=True); f = tmp / d / "codex"; f.write_text("#!/bin/sh\n"); f.chmod(0o755)
            home = tmp / "home"; (home / ".claude").mkdir(parents=True)
            paths = InstallPaths.for_home(home)
            args = argparse.Namespace(source=str(source), adopt_existing_workerbee=False, without_codex=False, no_host_wiring=False)
            env = {"PATH": f"{tmp / 'x-shims' / 'abc'}:{tmp / 'real'}"}
            with mock.patch.object(cli, "_paths", return_value=paths), mock.patch.dict(os.environ, env), \
                 mock.patch("agents_inc.install.runtime.tempfile.gettempdir", return_value=str(tmp / "t")):
                for _ in range(2):
                    self.assertEqual(cli.install(args), 0)
                    self.assertEqual(InstallReceipt.load(paths.receipt).codex_path, (tmp / "real" / "codex").resolve())

    def test_repair_over_existing_install_keeps_ownership(self):
        import argparse
        from agents_inc.install import cli
        from unittest import mock
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "source"; (source / "agents_inc").mkdir(parents=True)
            (source / "agents_inc" / "models.json").write_text("{}")
            for name in ("workerbee", "codex-bridge"):
                (source / "skills" / name).mkdir(parents=True); (source / "skills" / name / "SKILL.md").write_text("x")
            home = Path(raw) / "home"; (home / ".claude").mkdir(parents=True)
            paths = InstallPaths.for_home(home)
            args = argparse.Namespace(source=str(source), adopt_existing_workerbee=False, without_codex=True, no_host_wiring=False)
            with mock.patch.object(cli, "_paths", return_value=paths):
                self.assertEqual(cli.install(args), 0)
                (source / "skills" / "workerbee" / "SKILL.md").write_text("y")  # new release
                self.assertEqual(cli.install(args), 0)
            receipt = InstallReceipt.load(paths.receipt)
            owned = [item.path for item in receipt.owned_paths]
            self.assertEqual(len(owned), len(set(owned)))
            self.assertIn(paths.launcher, owned)
            self.assertIn(home / ".claude/AGENTS.md", owned)


class PackagedInstallTest(unittest.TestCase):
    def test_install_without_source_uses_package_data(self):
        import argparse
        from agents_inc.install import cli
        from unittest import mock
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            data = tmp / "data"
            for name in ("workerbee", "codex-bridge"):
                (data / "skills" / name).mkdir(parents=True); (data / "skills" / name / "SKILL.md").write_text("x")
            (data / "docs/governance").mkdir(parents=True); (data / "docs/governance/SCHEMA-3NF.md").write_text("s")
            home = tmp / "home"; (home / ".claude").mkdir(parents=True)
            paths = InstallPaths.for_home(home)
            args = argparse.Namespace(source=None, adopt_existing_workerbee=False, without_codex=True, no_host_wiring=False)
            with mock.patch.object(cli, "_paths", return_value=paths), \
                 mock.patch.object(cli.datafiles, "repo_file", side_effect=lambda rel: data / rel):
                self.assertEqual(cli.install(args), 0)
            self.assertTrue(paths.receipt.exists())
            self.assertEqual((paths.state / "source-checkout").read_text().strip(), "packaged")
            self.assertTrue(any(paths.releases.glob("*/skills/workerbee/SKILL.md")))

