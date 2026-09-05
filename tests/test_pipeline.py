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
        # Reviewer gets mismatched JSON → unparsed → status returned.
        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                  runner=fake_runner_factory(payload), review_enabled=True)
        self.assertEqual(r.status, "returned")
        self.assertEqual(r.report.matched, 5)
        self.assertEqual(r.receipt["source_integrity"], "pass")
        self.assertEqual(r.receipt["content_review"], "unparsed")

    def test_forged_quote_is_returned_with_failures(self):
        payload = {"claims": [{"text": "t", "quote": "rent weekly", "anchor": "tim#p3"}], "draft": "Brief. (p3)"}
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

    def test_fenced_json_is_parsed(self):
        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}
        fenced = f"```json\n{json.dumps(payload)}\n```"
        def runner(cmd, stdin_text, timeout=300): return WorkerResult("returned", fenced, "", 0)
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"}, runner=runner)
        self.assertEqual(r.status, "returned")
        self.assertEqual(r.receipt["source_integrity"], "pass")
        self.assertEqual(r.report.matched, 5)

    def test_prompt_numbers_paragraphs(self):
        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}
        captured_stdin = [None]
        def runner(cmd, stdin_text, timeout=300):
            captured_stdin[0] = stdin_text
            return WorkerResult("returned", json.dumps(payload), "", 0)
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"}, runner=runner)
        self.assertIn("[p1]", captured_stdin[0])
        self.assertIn("[p6]", captured_stdin[0])

    def test_empty_draft_is_returned(self):
        # Good claims, empty draft → status returned, receipt content_review == "draft_missing"
        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": ""}
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                  runner=fake_runner_factory(payload))
        self.assertEqual(r.status, "returned")
        self.assertEqual(r.receipt["content_review"], "draft_missing")

    def test_empty_claims_is_returned(self):
        # Empty claims list → verifier fails (0 checked), status returned with source_integrity fail
        payload = {"claims": [], "draft": "x (p2)"}
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                  runner=fake_runner_factory(payload))
        self.assertEqual(r.status, "returned")
        self.assertEqual(r.receipt["source_integrity"], "fail")

    def test_draft_citing_unanchored_paragraph_is_returned(self):
        # Good 5 claims (p2, p3, p4, p5, p6), draft cites p9 (unanchored)
        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Foo (p9)."}
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                  runner=fake_runner_factory(payload))
        self.assertEqual(r.status, "returned")
        self.assertEqual(r.receipt["content_review"], "uncited_draft")

    def test_verified_requires_reviewer_ok(self):
        good = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief summary (p2)."}
        calls = []
        def runner(cmd, stdin_text, timeout=300):
            calls.append(cmd[0])
            if len(calls) == 1:
                return WorkerResult("returned", json.dumps(good), "", 0)
            return WorkerResult("returned", json.dumps({"verdicts":[{"claim":i,"ok":True,"issue":""} for i in range(5)],"omissions":[]}), "", 0)
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"}, runner=runner)
        self.assertEqual(r.status, "verified")
        self.assertEqual(calls, ["claude", "codex"])
        self.assertEqual(r.receipt["content_review"], "pass")

    def test_reviewer_issue_is_needs_review(self):
        good = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}
        n = {"i": 0}
        def runner(cmd, stdin_text, timeout=300):
            n["i"] += 1
            if n["i"] == 1:
                return WorkerResult("returned", json.dumps(good), "", 0)
            return WorkerResult("returned", json.dumps({"verdicts":[
                {"claim":0,"ok":True,"issue":""},
                {"claim":1,"ok":True,"issue":""},
                {"claim":2,"ok":False,"issue":"Clause 8 overrides Clause 3"},
                {"claim":3,"ok":True,"issue":""},
                {"claim":4,"ok":True,"issue":""}
            ],"omissions":[]}), "", 0)
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"}, runner=runner)
        self.assertEqual(r.status, "needs-review")
        self.assertIn("Clause 8", json.dumps(r.receipt))

    def test_invalid_reviewer_is_returned(self):
        good = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}
        n = {"i": 0}
        def runner(cmd, stdin_text, timeout=300):
            n["i"] += 1
            if n["i"] == 1:
                return WorkerResult("returned", json.dumps(good), "", 0)
            return WorkerResult("returned", json.dumps({"verdicts":[{"claim":2,"ok":False,"issue":"Clause 8"}],"omissions":[]}), "", 0)
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"}, runner=runner)
        self.assertEqual(r.status, "returned")
        self.assertEqual(r.receipt["content_review"], "invalid")

    def test_single_vendor_is_returned(self):
        good = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude"}, runner=fake_runner_factory(good))
        self.assertEqual(r.status, "returned")
        self.assertEqual(r.receipt["content_review"], "no_other_vendor")

    def test_worker_provider_preference(self):
        good = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}
        captured_cmd = [None]
        def runner(cmd, stdin_text, timeout=300):
            captured_cmd[0] = cmd
            return WorkerResult("returned", json.dumps(good), "", 0)
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude", "codex"},
                  worker_provider="codex", review_enabled=False, runner=runner)
        self.assertEqual(r.route.provider, "codex")
        self.assertEqual(captured_cmd[0][0], "codex")

    def test_pipeline_uncited_sentence_caps_needs_review(self):
        # Good claims verify, but draft has uncited sentence → status needs-review (not verified)
        good = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]],
                "draft": "Cited claim (p2). Uncited claim. More cited (p3)."}
        def runner(cmd, stdin_text, timeout=300):
            if "codex" in cmd:  # Reviewer
                return WorkerResult("returned", json.dumps({"verdicts":[
                    {"claim":i,"ok":True,"issue":""} for i in range(5)
                ],"omissions":[]}), "", 0)
            # Worker
            return WorkerResult("returned", json.dumps(good), "", 0)
        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"}, runner=runner)
        self.assertEqual(r.status, "needs-review")
        self.assertIn("uncited_sentences", r.receipt)
        self.assertGreater(len(r.receipt.get("uncited_sentences", [])), 0)
