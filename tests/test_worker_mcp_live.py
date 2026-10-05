"""D54 live proof: a broker Worker asks its Lead through ask_lead, the Lead answers, the Worker uses the answer.

One haiku Worker and one luna Worker. Each asks "what is the password word"; the test answers "pelican" and the
Worker report must contain it. Skipped unless AGENTS_INC_LIVE_ASK=1. Quota exhaustion skips with evidence.
Run: AGENTS_INC_LIVE_ASK=1 python3 -m unittest tests.test_worker_mcp_live
"""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agents_inc.install import mcp_broker

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "skills/workerbee/tests/fixtures/example_slots.json"
QUOTA_RE = re.compile(r"usage limit|rate limit|too many requests|\b429\b|quota", re.IGNORECASE)
REPORT = ("caveman NOT installed -> checked by hand. GRILL: none. [verified] gate rc=0 exit code 0.\n"
          "PASSWORD: ANSWER\nOUT OF SCOPE / INCOMPLETE: none\nWORKERS SPAWNED: 0")


@unittest.skipUnless(os.environ.get("AGENTS_INC_LIVE_ASK") == "1", "set AGENTS_INC_LIVE_ASK=1")
class LiveAskLeadTest(unittest.TestCase):
    def _ask_round_trip(self, model: str, cli: str) -> None:
        if not shutil.which(cli):
            self.skipTest(f"{cli} CLI not on PATH")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            cwd = root / "repo"
            cwd.mkdir()
            (cwd / "README.md").write_text("ask probe\n")
            for cmd in (["git", "init", "-q"], ["git", "add", "README.md"],
                        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"]):
                subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)
            run_dir = root / "lead-run"
            run_dir.mkdir()
            (run_dir / "run.json").write_text(json.dumps({
                "schema_version": 1, "run_id": f"live-ask-{model}", "model": "terra", "effort": "high",
                "cwd": str(cwd), "chain": ["CoS", "terra"], "worker_models": [model], "permission_mode": "default",
                "fan_out": {"width": 1, "total": 1, "depth": 1}}))
            slots = json.loads(EXAMPLE.read_text())
            slots["TASK"] = ("You do not know the password word; only your Lead does. Call the ask_lead tool (see LEAD "
                             "CHANNEL below) exactly once with the question: what is the password word. Then reply "
                             "with these lines verbatim as plain text, with ANSWER replaced by the Lead's answer:\n"
                             + REPORT)
            slots["SUCCESS_GATE"] = "`grep -c PASSWORD` on the reply prints 1 and the line carries the Lead's answer."
            slots["FAILURE_GATE"] = "`grep -c PASSWORD` on the reply prints 0, or no ask_lead call was made: report RED."
            slots["PRE_EXISTING_CHANGES"] = "none: no writes."
            broker = mcp_broker.Broker(run_dir)
            asked, is_error, note = broker.tool_dispatch({"model": model, "effort": "low", "slots": slots})
            print(f"\n{model} DISPATCH:", json.dumps(asked, indent=1)[-2500:], file=sys.stderr)
            if asked.get("status") != "needs-lead" and QUOTA_RE.search(json.dumps(asked)):
                self.skipTest("quota exhausted (evidence): " + json.dumps(asked)[-300:])
            self.assertEqual(asked.get("status"), "needs-lead", asked)
            self.assertIn("password word", asked["question"].lower())
            ok, is_error, _ = broker.tool_answer({"request_id": asked["request_id"], "question_n": asked["question_n"],
                                                  "text": "pelican"})
            self.assertFalse(is_error, ok)
            done, is_error, _ = broker.tool_wait({"request_id": asked["request_id"], "timeout": 900})
            print(f"{model} RESULT:", json.dumps(done, indent=1)[-2500:], file=sys.stderr)
            self.assertIn("pelican", done.get("report", "").lower(), done)
            spec = json.loads((run_dir / "run.json").read_text())
            self.assertEqual(spec["questions"], 1)

    def test_haiku_asks_lead(self):
        self._ask_round_trip("haiku", "claude")

    def test_luna_asks_lead(self):
        self._ask_round_trip("luna", "codex")


if __name__ == "__main__":
    unittest.main()
