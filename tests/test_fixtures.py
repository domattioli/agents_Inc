import json, unittest
from pathlib import Path
from workerbees.verifier import verify, passed

FIX = Path(__file__).resolve().parent.parent / "fixtures"

class FixtureTest(unittest.TestCase):
    def _check(self, name, src_file):
        src = (FIX / name / src_file).read_text()
        exp = json.loads((FIX / name / "expected.json").read_text())
        faults = json.loads((FIX / name / "faults.json").read_text())
        good = [dict(text="", **c) for c in exp["required_claims"]]
        bad = [dict(text="", **c) for c in faults["forged"]]
        self.assertTrue(passed(verify(src, name, good)), "expected claims must verify")
        r = verify(src, name, bad)
        self.assertEqual(r.matched, 0, "every seeded fault must fail")
        self.assertGreaterEqual(len(bad), 3)

    def test_tim(self): self._check("tim", "matter.md")
    def test_dom(self): self._check("dom", "design.md")
