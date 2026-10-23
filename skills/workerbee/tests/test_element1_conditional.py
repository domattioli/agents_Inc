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
        report = ("caveman ultra confirmed\nGRILL: none\n[verified] gate ran, exit code 0\n"
                  "OUT OF SCOPE / INCOMPLETE: none\nWORKERS SPAWNED: 0\n")
        r = self._run(report, ("--profile", "report"))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "COMPLIANT")
        self.assertIn("handoff-lint NOT installed", r.stderr)

    def test_report_profile_accepts_caveman_declaration_line(self):
        for decl in ("caveman: ultra", "caveman: not installed -> by hand"):
            report = (decl + "\nGRILL: none\n[verified] gate ran, exit code 0\n"
                      "OUT OF SCOPE / INCOMPLETE: none\nWORKERS SPAWNED: 0\n")
            r = self._run(report, ("--profile", "report"))
            self.assertEqual(r.returncode, 0, decl)
            self.assertEqual(r.stdout.strip(), "COMPLIANT", decl)


class TestVerifiedExitLine(unittest.TestCase):
    """#91: the contract's own no-gate line must not trip verified-exit-without-code."""
    BASE = "caveman ultra. grill. [verified] exit code 0.\nOUT OF SCOPE / INCOMPLETE: none\nWORKERS SPAWNED: 0\n"

    def _flagged(self, line):
        return "verified-exit-without-code" in cdp.check_report(self.BASE + line + "\n")

    def test_contract_no_gate_line_not_flagged(self):
        self.assertFalse(self._flagged("[verified] Gate commands: none, exit code N/A. "
                                       "Snapshot integrity unverified; success gate not established."))

    def test_exit_as_plain_word_not_flagged(self):
        self.assertFalse(self._flagged("[verified] Exit gate needs 10 scored, so the debate continues."))

    def test_exit_with_value_not_flagged(self):
        self.assertFalse(self._flagged("[verified] tests exit 0"))

    def test_exited_without_code_flagged(self):
        self.assertTrue(self._flagged("the gate exited cleanly [verified]"))

    def test_exit_code_without_value_flagged(self):
        self.assertTrue(self._flagged("[verified] gate exit code"))


if __name__ == "__main__":
    unittest.main()
