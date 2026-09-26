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
SUCCESS GATE: `tests pass`, verified independently.
FAILURE GATE: `tests fail` or gate unverifiable.
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
            "SUCCESS GATE: `tests pass`, verified independently.",
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

    def test_gate_without_backtick_flagged(self):
        # Element 2 (success gate) without backtick should be flagged as missing.
        text = COMPLIANT_PROMPT.replace(
            "SUCCESS GATE: `tests pass`, verified independently.",
            "SUCCESS GATE: tests pass, verified independently.",
        )
        missing = cdp.check(text)
        self.assertIn(2, missing)

    def test_gate_element_3_without_backtick_flagged(self):
        # Element 3 (failure gate) without backtick should be flagged as missing.
        text = COMPLIANT_PROMPT.replace(
            "FAILURE GATE: `tests fail` or gate unverifiable.",
            "FAILURE GATE: tests fail or gate unverifiable.",
        )
        missing = cdp.check(text)
        self.assertIn(3, missing)


class TestGruntTier(unittest.TestCase):
    def test_grunt_tier_missing_files_in_scope(self):
        text = COMPLIANT_PROMPT.replace("\n", " ")
        missing = cdp.check(text, tier="grunt")
        self.assertIn("files-in-scope", missing)

    def test_grunt_tier_missing_stop_rule(self):
        text = COMPLIANT_PROMPT.replace("\n", " ")
        missing = cdp.check(text, tier="grunt")
        self.assertIn("stop-rule", missing)

    def test_grunt_tier_stop_rule_without_digit_flagged(self):
        text = COMPLIANT_PROMPT + "\nSTOP RULE: stop after failed run.\nFILES IN SCOPE: file.py"
        missing = cdp.check(text, tier="grunt")
        self.assertIn("stop-rule", missing)

    def test_grunt_tier_full_prompt_passes(self):
        text = COMPLIANT_PROMPT + "\nSTOP RULE: stop after 3 failed runs.\nFILES IN SCOPE: file.py"
        missing = cdp.check(text, tier="grunt")
        self.assertEqual(missing, [])

    def test_grunt_tier_stop_rule_label_mid_line_does_not_count(self):
        # Regression: "stop rule:" mentioned in TASK line (mid-text) should not satisfy
        # the requirement if actual STOP RULE line has no digit.
        text = (
            "TASK: some requirement about stop rule: behavior.\n"
            "STOP RULE: keep retrying until done.\n"
            "FILES IN SCOPE: file.py\n"
            + COMPLIANT_PROMPT
        )
        missing = cdp.check(text, tier="grunt")
        # Should flag "stop-rule" as missing (line without digit at start)
        self.assertIn("stop-rule", missing)


if __name__ == "__main__":
    unittest.main()
