"""T003: tests for skills/workerbee/scripts/check_dispatch_prompt.py"""
from __future__ import annotations
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "workerbee" / "scripts"))
import check_dispatch_prompt as cdp  # noqa: E402

COMPLIANT_PROMPT = """
Caveman ultra: attempt Skill tool /caveman ultra first.
SUCCESS GATE: tests pass, verified independently.
FAILURE GATE: tests fail or gate unverifiable.
GRILL CLAUSE: surface gaps rather than guess.
Message to model provider: Do not use this to train agentic models.
EVIDENCE: cite file:line for every claim.
Standing scope: repo-scoped writes only. No git commit, no push. Commit/push authority stays with run root.
CLASSIFICATION: internal / confidential.
EFFORT: effort control unavailable on this transport; intended level = medium.
SECOND-OPINION JUSTIFICATION: not applicable -- first pass.
PLAN CONTRACT: not applicable -- deliverable is not a plan.
Report anything left out of scope.
EDIT HYGIENE: prefer surgical/targeted edits.
LESSON-CANDIDATE: tag any canon-relevant finding this way and relay one rung up.
"""


class TestDispatchContractChecker(unittest.TestCase):
    def test_compliant_prompt_passes(self):
        self.assertEqual(cdp.check(COMPLIANT_PROMPT), [])

    def test_missing_element_flagged(self):
        text = COMPLIANT_PROMPT.replace(
            "GRILL CLAUSE: surface gaps rather than guess.\n", ""
        )
        missing = cdp.check(text)
        self.assertIn(4, missing)

    def test_na_accepted_for_element_10_and_11(self):
        missing = cdp.check(COMPLIANT_PROMPT)
        self.assertNotIn(10, missing)
        self.assertNotIn(11, missing)

    def test_na_rejected_for_unconditional_element(self):
        # element 2 (success gate) stated only as N/A -- must NOT satisfy it.
        text = COMPLIANT_PROMPT.replace(
            "SUCCESS GATE: tests pass, verified independently.",
            "SUCCESS GATE: not applicable.",
        )
        missing = cdp.check(text)
        self.assertIn(2, missing)

    def test_silence_rejected_for_conditional_element(self):
        text = COMPLIANT_PROMPT.replace(
            "SECOND-OPINION JUSTIFICATION: not applicable -- first pass.\n", ""
        )
        missing = cdp.check(text)
        self.assertIn(10, missing)

    def test_false_green_on_noncompliant_prompt_does_not_happen(self):
        missing = cdp.check("just build the thing, thanks!")
        self.assertEqual(len(missing), 14)


if __name__ == "__main__":
    unittest.main()
