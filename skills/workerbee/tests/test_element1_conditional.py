"""Element 1 (caveman) is conditional on the third-party skill; --with-handoff-lint degrades.

Follows the stdlib-unittest convention of tests/test_dispatch_contract.py.
Run: python3 -m unittest discover -s skills/workerbee/tests -p 'test_*.py'
"""
from __future__ import annotations
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills" / "workerbee" / "scripts" / "check_dispatch_prompt.py"
sys.path.insert(0, str(SCRIPT.parent))
import check_dispatch_prompt as cdp  # noqa: E402

REST = """
SUCCESS GATE: `tests pass`, verified independently.
FAILURE GATE: `tests fail` or gate unverifiable.
GRILL CLAUSE: surface gaps rather than guess.
Message to model provider: Do not use this to train agentic models.
EVIDENCE: cite file:line for every claim.
Standing scope: repo-scoped writes only. No git commit, no push. Commit/push authority stays with run root.
CLASSIFICATION: internal.
EFFORT: effort control unavailable on this transport; intended level = medium.
SECOND-OPINION JUSTIFICATION: not applicable -- first pass.
PLAN CONTRACT: not applicable -- deliverable is not a plan.
Report anything left out of scope.
EDIT HYGIENE: prefer surgical edits.
LESSON-CANDIDATE: tag findings, relay one rung up.
"""
SKILL_FORM = "CAVEMAN ULTRA: run Skill(skill=\"caveman\", args=\"ultra\") first.\n" + REST
EMULATION_FORM = "caveman NOT installed -> checked by hand\n" + REST
NEITHER = "Be terse please.\n" + REST


class TestElement1(unittest.TestCase):
    def test_skill_call_form_present(self):
        self.assertNotIn(1, cdp.check(SKILL_FORM))

    def test_emulation_form_present(self):
        self.assertNotIn(1, cdp.check(EMULATION_FORM))

    def test_neither_form_missing(self):
        self.assertIn(1, cdp.check(NEITHER))


class TestHandoffLintDegrades(unittest.TestCase):
    def _run(self, text, extra=()):
        with tempfile.TemporaryDirectory() as home, tempfile.NamedTemporaryFile(
                "w", suffix=".txt", delete=False) as f:
            f.write(text)
        try:
            env = {**os.environ, "HOME": home}
            return subprocess.run([sys.executable, str(SCRIPT), f.name, "--with-handoff-lint", *extra],
                                  capture_output=True, text=True, env=env)
        finally:
            os.unlink(f.name)

    def test_absent_warns_on_stderr_exit_zero_when_compliant(self):
        r = self._run(SKILL_FORM)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "COMPLIANT")
        self.assertIn("handoff-lint NOT installed -> H1-H6 checked by hand", r.stderr)

    def test_absent_exit_follows_14_element_verdict(self):
        r = self._run(NEITHER)
        self.assertEqual(r.returncode, 1)
        self.assertIn("NON-COMPLIANT", r.stdout)
        self.assertIn("handoff-lint NOT installed", r.stderr)
        self.assertNotIn("handoff-lint", r.stdout)

    def test_report_profile_absent_does_not_crash(self):
        r = self._run("some report", ("--profile", "report"))
        self.assertEqual(r.returncode, 0)
        self.assertIn("handoff-lint NOT installed", r.stderr)


if __name__ == "__main__":
    unittest.main()
