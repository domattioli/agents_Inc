import tempfile
import unittest
from pathlib import Path

from agents_inc.install.bundle import activate, stage_bundle, verify_bundle
from agents_inc.install.paths import InstallPaths
from agents_inc.install.receipt import InstallReceipt


class BundleTest(unittest.TestCase):
    def test_stage_is_allowlisted_and_activation_uses_current_link(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = root / "source"; home = root / "home"
            (source / "agents_inc").mkdir(parents=True); (source / "agents_inc" / "models.json").write_text("{}")
            (source / "skills" / "workerbee").mkdir(parents=True); (source / "skills" / "workerbee" / "SKILL.md").write_text("skill")
            (source / "skills" / "codex-bridge").mkdir(parents=True); (source / "skills" / "codex-bridge" / "SKILL.md").write_text("skill")
            (source / ".env").write_text("not bundled")
            staged = stage_bundle(source, InstallPaths.for_home(home))
            self.assertTrue((staged.path / "agents_inc/models.json").is_file())
            self.assertFalse((staged.path / ".env").exists())
            self.assertTrue(verify_bundle(staged.path))
            receipt = InstallReceipt(staged.digest, Path("/usr/bin/python3"), Path("/usr/bin/codex"))
            activate(staged, InstallPaths.for_home(home), receipt)
            self.assertTrue((home / ".local/share/agents-inc/current").is_symlink())
