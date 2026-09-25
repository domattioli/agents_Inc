import unittest
from pathlib import Path

from agents_inc.install.paths import InstallPaths


class InstallPathsTest(unittest.TestCase):
    def test_for_home_uses_documented_user_scope_locations(self):
        paths = InstallPaths.for_home(Path("/Users/tester"))
        self.assertEqual(paths.releases, Path("/Users/tester/.local/share/agents-inc/releases"))
        self.assertEqual(paths.current, Path("/Users/tester/.local/share/agents-inc/current"))
        self.assertEqual(paths.launcher, Path("/Users/tester/.local/bin/agents-inc"))
        self.assertEqual(paths.receipt, Path("/Users/tester/.config/agents-inc/install.json"))
        self.assertEqual(paths.state, Path("/Users/tester/.local/state/agents-inc"))
        self.assertEqual(paths.claude_skills, Path("/Users/tester/.claude/skills"))
        self.assertEqual(paths.codex_skills, Path("/Users/tester/.agents/skills"))

    def test_relative_home_is_rejected(self):
        with self.assertRaises(ValueError):
            InstallPaths.for_home(Path("relative-home"))
