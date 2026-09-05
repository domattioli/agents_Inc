import unittest
from workerbees.bench import summarize

class BenchTest(unittest.TestCase):
    def test_summary_has_no_percent_claim_and_zero_dollars(self):
        rows = [{"fixture":"tim","provider":"claude","tier":"cheap","model":"haiku","status":"verified","checked":5,"matched":5,"reviewer":"ok","seconds":12.0,"accepted":True},
                {"fixture":"tim","provider":"claude","tier":"frontier","model":"fable","status":"needs-review","checked":5,"matched":5,"reviewer":"disabled","seconds":30.0,"accepted":True}]
        md = summarize(rows)
        self.assertIn("incremental dollars: 0", md)
        self.assertNotIn("%", md)
        self.assertIn("claude/cheap", md)
