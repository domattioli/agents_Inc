import json, unittest
from workerbees.reviewer import review
from workerbees.adapters.base import WorkerResult

SRC = "Clause 3. Rent monthly.\n\nClause 8. Rent quarterly."
CLAIMS = [{"text": "monthly", "quote": "Rent monthly", "anchor": "x#p1"}]

def runner_with(payload, status="returned"):
    def r(cmd, stdin_text, timeout=300):
        return WorkerResult(status, json.dumps(payload) if payload is not None else "junk", "", 0)
    return r

class ReviewerTest(unittest.TestCase):
    def test_all_ok_no_omissions(self):
        res = review(SRC, "x", CLAIMS, "Rent is monthly (p1).", "claude", {"claude","codex"}, False,
                     runner=runner_with({"verdicts":[{"claim":0,"ok":True,"issue":""}],"omissions":[]}))
        self.assertEqual(res.status, "ok")

    def test_issue_flags(self):
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude","codex"}, False,
                     runner=runner_with({"verdicts":[{"claim":0,"ok":False,"issue":"Clause 8 overrides"}],"omissions":["Clause 8"]}))
        self.assertEqual(res.status, "issues")
        self.assertEqual(res.omissions, ["Clause 8"])

    def test_same_vendor_only_is_no_other_vendor(self):
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude"}, False, runner=runner_with({}))
        self.assertEqual(res.status, "no_other_vendor")

    def test_reviewer_uses_other_provider(self):
        seen = {}
        def r(cmd, stdin_text, timeout=300):
            seen["cmd"] = cmd
            return WorkerResult("returned", json.dumps({"verdicts":[],"omissions":[]}), "", 0)
        review(SRC, "x", CLAIMS, "d", "claude", {"claude","codex"}, False, runner=r)
        self.assertEqual(seen["cmd"][0], "codex")

    def test_unparsed(self):
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude","codex"}, False, runner=runner_with(None))
        self.assertEqual(res.status, "unparsed")

    def test_empty_verdicts_is_issues(self):
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude","codex"}, False,
                     runner=runner_with({"verdicts":[],"omissions":[]}))
        self.assertEqual(res.status, "issues")
        self.assertTrue(any("reviewer_incomplete" in o for o in res.omissions))

    def test_string_true_is_issues(self):
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude","codex"}, False,
                     runner=runner_with({"verdicts":[{"claim":0,"ok":"true","issue":""}],"omissions":[]}))
        self.assertEqual(res.status, "issues")
        self.assertTrue(any("reviewer_incomplete" in o for o in res.omissions))

    def test_duplicate_claim_ids_is_issues(self):
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude","codex"}, False,
                     runner=runner_with({"verdicts":[{"claim":0,"ok":True,"issue":""},{"claim":0,"ok":True,"issue":""}],"omissions":[]}))
        self.assertEqual(res.status, "issues")
        self.assertTrue(any("reviewer_incomplete" in o and "not unique" in o for o in res.omissions))

    def test_missing_claim_is_issues(self):
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude","codex"}, False,
                     runner=runner_with({"verdicts":[],"omissions":[]}))
        self.assertEqual(res.status, "issues")
        self.assertTrue(any("reviewer_incomplete" in o for o in res.omissions))
