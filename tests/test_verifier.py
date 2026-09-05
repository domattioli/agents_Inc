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

if __name__ == "__main__":
    unittest.main()
