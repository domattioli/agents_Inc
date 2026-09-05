import unittest
from workerbees.verifier import verify, passed

SRC = "Clause 3. Tenant pays rent monthly.\n\nClause 8. Tenant pays rent quarterly."

class VerifierTest(unittest.TestCase):
    def test_exact_quote_in_right_paragraph_matches(self):
        r = verify(SRC, "lease", [{"text": "rent is monthly", "quote": "pays rent monthly", "anchor": "lease#p1"}])
        self.assertEqual((r.checked, r.matched), (1, 1))
        self.assertTrue(passed(r))

    def test_forged_quote_fails(self):
        r = verify(SRC, "lease", [{"text": "x", "quote": "pays rent weekly", "anchor": "lease#p1"}])
        self.assertFalse(passed(r))
        self.assertEqual(r.failures[0]["reason"], "quote_not_in_anchor")

    def test_wrong_anchor_fails(self):
        r = verify(SRC, "lease", [{"text": "x", "quote": "pays rent monthly", "anchor": "lease#p2"}])
        self.assertEqual(r.failures[0]["reason"], "quote_not_in_anchor")

    def test_bad_anchor_format_fails(self):
        r = verify(SRC, "lease", [{"text": "x", "quote": "Clause", "anchor": "lease#zz"}])
        self.assertEqual(r.failures[0]["reason"], "bad_anchor")

    def test_hash_is_sha256(self):
        self.assertEqual(len(verify(SRC, "lease", []).source_hash), 64)

    def test_zero_claims_not_passed(self):
        r = verify(SRC, "lease", [])
        self.assertEqual(r.checked, 0)
        self.assertEqual(r.matched, 0)
        self.assertFalse(passed(r))

    def test_negation_prefix_forgery_fails(self):
        # "unsigned 16-bit" should not match quote "signed 16-bit"
        SRC2 = "This is an unsigned 16-bit value."
        r = verify(SRC2, "spec", [{"text": "x", "quote": "signed 16-bit", "anchor": "spec#p1"}])
        self.assertFalse(passed(r))
        self.assertEqual(r.failures[0]["reason"], "quote_not_in_anchor")

class CheckDraftTest(unittest.TestCase):
    def test_check_draft_counts_cited(self):
        from workerbees.verifier import check_draft
        draft = "Paragraph one (p2). Paragraph two (p3). Paragraph three (p4)."
        result = check_draft(draft, {"2", "3", "4"})
        self.assertEqual(result["sentences"], 3)
        self.assertEqual(result["cited"], 3)
        self.assertEqual(result["uncited_sentences"], [])
        self.assertEqual(result["bad_citations"], [])

    def test_check_draft_flags_uncited_sentence(self):
        from workerbees.verifier import check_draft
        draft = "Paragraph one (p2). Paragraph two. Paragraph three (p4)."
        result = check_draft(draft, {"2", "3", "4"})
        self.assertEqual(result["sentences"], 3)
        self.assertEqual(result["cited"], 2)
        self.assertIn("Paragraph two.", result["uncited_sentences"])
        self.assertEqual(result["bad_citations"], [])

    def test_check_draft_bad_citation(self):
        from workerbees.verifier import check_draft
        draft = "Paragraph one (p2). Paragraph two (p9)."
        result = check_draft(draft, {"2", "3"})
        self.assertEqual(result["sentences"], 2)
        self.assertEqual(result["cited"], 2)
        self.assertIn("9", result["bad_citations"])

if __name__ == "__main__":
    unittest.main()
