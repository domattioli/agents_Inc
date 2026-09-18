import tempfile
import unittest
from pathlib import Path

from agents_inc.install.discovery import install_skill_links, restore_skill_links
from agents_inc.install.paths import InstallPaths
from agents_inc.install.receipt import InstallReceipt


class DiscoveryTest(unittest.TestCase):
    def test_installs_both_skills_for_both_hosts_and_restores_adoption(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"; paths = InstallPaths.for_home(home); release = home / "release"
            for name in ("workerbee", "codex-bridge"):
                (release / "skills" / name).mkdir(parents=True)
            old = home / "old-workerbee"; old.mkdir(parents=True); paths.claude_skills.mkdir(parents=True)
            (paths.claude_skills / "workerbee").symlink_to(old)
            receipt = InstallReceipt("a" * 64, Path("/usr/bin/python3"), Path("/usr/bin/codex"))
            receipt = install_skill_links(paths, release, receipt, adopt_existing_workerbee=True)
            for directory in (paths.claude_skills, paths.codex_skills):
                for name in ("workerbee", "codex-bridge"):
                    self.assertTrue((directory / name).is_symlink())
            restore_skill_links(paths, receipt)
            self.assertEqual((paths.claude_skills / "workerbee").resolve(), old.resolve())

    def test_foreign_collision_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"; paths = InstallPaths.for_home(home); release = home / "release"
            (release / "skills" / "workerbee").mkdir(parents=True); (release / "skills" / "codex-bridge").mkdir(parents=True)
            (paths.codex_skills / "workerbee").mkdir(parents=True)
            receipt = InstallReceipt("a" * 64, Path("/usr/bin/python3"), Path("/usr/bin/codex"))
            with self.assertRaisesRegex(RuntimeError, "WB_CONFIG_CONFLICT"):
                install_skill_links(paths, release, receipt)

    def test_restore_preserves_replaced_managed_link_and_unrelated_paths(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"; paths = InstallPaths.for_home(home); release = home / "release"
            for name in ("workerbee", "codex-bridge"):
                (release / "skills" / name).mkdir(parents=True)
            receipt = InstallReceipt("a" * 64, Path("/usr/bin/python3"), Path("/usr/bin/codex"))
            receipt = install_skill_links(paths, release, receipt)
            managed = paths.codex_skills / "workerbee"; managed.unlink(); managed.symlink_to("/replacement")
            unrelated = paths.codex_skills / "unrelated"; unrelated.mkdir()
            retained = restore_skill_links(paths, receipt)
            self.assertEqual(managed.readlink(), Path("/replacement"))
            self.assertTrue(unrelated.is_dir())
            self.assertIn(managed, retained)
