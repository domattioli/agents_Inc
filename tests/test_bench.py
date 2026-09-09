import unittest
from workerbees.bench import summarize

class BenchTest(unittest.TestCase):
    def test_summary_has_no_percent_claim_and_reports_unknown_cost(self):
        rows = [{"fixture":"sample-b","provider":"claude","tier":"grunt","model":"haiku","status":"verified","checked":5,"matched":5,"reviewer":"ok","seconds":12.0,"accepted":True,"verifier_pass":True,"review":"pass"},
                {"fixture":"sample-b","provider":"claude","tier":"executive","model":"fable","status":"needs-review","checked":5,"matched":5,"reviewer":"disabled","seconds":30.0,"accepted":False,"verifier_pass":True,"review":"not-run"}]
        md = summarize(rows)
        self.assertIn("incremental cost: unknown", md)
        self.assertNotIn("%", md)
        self.assertIn("claude/grunt", md)
        self.assertIn("verifier_pass", md)
        self.assertIn("Frontier baseline runs without a Reviewer", md)

    def test_frontier_baseline_cannot_reach_accepted(self):
        rows = [{"fixture":"sample-b","provider":"codex","tier":"executive","model":"gpt-6-astra","status":"returned","checked":5,"matched":5,"reviewer":"disabled","seconds":17.0,"accepted":False,"verifier_pass":True,"review":"not-run"}]
        md = summarize(rows)
        self.assertIn("Frontier baseline runs without a Reviewer", md)

    def test_summary_status_tally(self):
        rows = [
            {"fixture":"sample-b","provider":"claude","tier":"grunt","model":"haiku","status":"verified","checked":5,"matched":5,"reviewer":"ok","seconds":12.0,"accepted":True,"verifier_pass":True,"review":"pass","corrections":0,"paused_reason":None},
            {"fixture":"sample-b","provider":"claude","tier":"grunt","model":"haiku","status":"needs-review","checked":5,"matched":5,"reviewer":"ok","seconds":14.0,"accepted":True,"verifier_pass":True,"review":"pass","corrections":1,"paused_reason":None},
            {"fixture":"sample-a","provider":"claude","tier":"grunt","model":"haiku","status":"verified","checked":3,"matched":3,"reviewer":"ok","seconds":10.0,"accepted":True,"verifier_pass":True,"review":"pass","corrections":0,"paused_reason":None},
            {"fixture":"sample-b","provider":"codex","tier":"grunt","model":"haiku","status":"returned","checked":5,"matched":5,"reviewer":"ok","seconds":20.0,"accepted":False,"verifier_pass":True,"review":"fail","corrections":0,"paused_reason":"quota"}
        ]
        md = summarize(rows)
        self.assertIn("statuses:", md)
        self.assertIn("verified: 2", md)
        self.assertIn("needs-review: 1", md)
        self.assertIn("returned: 1", md)
        self.assertIn("corrections_mean: 0.3", md)
        self.assertIn("observed subscription calls: 8", md)
        self.assertIn("observed subscription calls: 2", md)
