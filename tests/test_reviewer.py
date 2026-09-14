import json, unittest
from agents_inc.reviewer import review as _review
from agents_inc.adapters.base import WorkerResult
from codex_testkit import CODEX_EXECUTABLE

SRC = "Clause 3. Rent monthly.\n\nClause 8. Rent quarterly."
CLAIMS = [{"text": "monthly", "quote": "Rent monthly", "anchor": "x#p1"}]

def review(*args, **kwargs):
    kwargs.setdefault("codex_executable", str(CODEX_EXECUTABLE))
    return _review(*args, **kwargs)

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
        review(SRC, "x", CLAIMS, "d", "claude", {"claude","codex"}, False, runner=r,
               codex_executable=str(CODEX_EXECUTABLE))
        self.assertEqual(seen["cmd"][0], str(CODEX_EXECUTABLE))

    def test_codex_route_without_executable_fails_closed(self):
        res = _review(SRC, "x", CLAIMS, "d", "claude", {"claude", "codex"}, False,
                     runner=runner_with({}))
        self.assertEqual(res.status, "blocked")
        self.assertIn("WB_CLI_NOT_FOUND", res.raw)

    def test_unparsed(self):
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude","codex"}, False, runner=runner_with(None))
        self.assertEqual(res.status, "unparsed")

    def test_empty_verdicts_is_invalid(self):
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude","codex"}, False,
                     runner=runner_with({"verdicts":[],"omissions":[]}))
        self.assertEqual(res.status, "invalid")

    def test_string_true_is_invalid(self):
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude","codex"}, False,
                     runner=runner_with({"verdicts":[{"claim":0,"ok":"true","issue":""}],"omissions":[]}))
        self.assertEqual(res.status, "invalid")

    def test_duplicate_claim_ids_is_invalid(self):
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude","codex"}, False,
                     runner=runner_with({"verdicts":[{"claim":0,"ok":True,"issue":""},{"claim":0,"ok":True,"issue":""}],"omissions":[]}))
        self.assertEqual(res.status, "invalid")

    def test_missing_claim_is_invalid(self):
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude","codex"}, False,
                     runner=runner_with({"verdicts":[],"omissions":[]}))
        self.assertEqual(res.status, "invalid")
