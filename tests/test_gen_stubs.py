import tempfile, unittest
from pathlib import Path
from workerbees.hosts.gen_stubs import generate

CANON = Path(__file__).resolve().parent.parent / "skills" / "workerbees" / "SKILL.md"

class StubTest(unittest.TestCase):
    def test_both_hosts_get_identical_body(self):
        root = Path(tempfile.mkdtemp())
        out = generate(CANON, root)
        self.assertEqual({p.relative_to(root).as_posix() for p in out},
                         {".claude/skills/workerbees/SKILL.md", ".agents/skills/workerbees/SKILL.md"})
        bodies = [p.read_text().split("---", 2)[2] for p in out]
        self.assertEqual(bodies[0], bodies[1])

    def test_canonical_under_180_tokens_approx(self):
        words = len(CANON.read_text().split())
        self.assertLessEqual(words, 140, "entry skill must stay ≤180 tokens (~140 words)")
