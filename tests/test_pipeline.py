import json, tempfile, unittest
from pathlib import Path
from workerbees.pipeline import brief
from workerbees.adapters.base import WorkerResult

FIX = Path(__file__).resolve().parent.parent / "fixtures"

def fake_runner_factory(payload: dict, status="returned"):
    def runner(cmd, stdin_text, timeout=300):
        return WorkerResult(status, json.dumps(payload), "", 0 if status == "returned" else 1)
    return runner

class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())
        self.exp = json.loads((FIX / "tim" / "expected.json").read_text())

    def test_good_worker_output_is_needs_review_not_verified(self):
        # Phase 1 has Verifier but no Reviewer → best status is needs-review.
        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief."}
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                  runner=fake_runner_factory(payload))
        self.assertEqual(r.status, "needs-review")
        self.assertEqual(r.report.matched, 5)
        self.assertEqual(r.receipt["source_integrity"], "pass")

    def test_forged_quote_is_returned_with_failures(self):
        payload = {"claims": [{"text": "t", "quote": "rent weekly", "anchor": "tim#p3"}], "draft": "Brief."}
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                  runner=fake_runner_factory(payload))
        self.assertEqual(r.status, "returned")
        self.assertEqual(r.receipt["source_integrity"], "fail")

    def test_quota_pauses(self):
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                  runner=fake_runner_factory({}, status="paused"))
        self.assertEqual(r.status, "paused")

    def test_only_optional_and_unauthorized_is_blocked(self):
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"gemini"},
                  runner=fake_runner_factory({}))
        self.assertEqual(r.status, "blocked")

    def test_non_json_worker_output_is_returned(self):
        def runner(cmd, stdin_text, timeout=300): return WorkerResult("returned", "not json", "", 0)
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude"}, runner=runner)
        self.assertEqual(r.status, "returned")
        self.assertEqual(r.receipt["source_integrity"], "unparsed")
