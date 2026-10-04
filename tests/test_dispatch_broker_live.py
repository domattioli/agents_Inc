"""D51 live proof: one real haiku Worker through `agents-inc dispatch --serve`.

Run: AGENTS_INC_LIVE_BROKER=1 python3 -m unittest tests.test_dispatch_broker_live
Skipped unless AGENTS_INC_LIVE_BROKER=1. Quota exhaustion skips with evidence; never a paid fallback.
"""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "skills/workerbee/tests/fixtures/example_slots.json"
REPORT = ("caveman NOT installed -> checked by hand. GRILL: none. [verified] gate rc=0 exit code 0.\n"
          "SSH_PROBE: SSH_RESULT\nREADME_PROBE: README_LINE\n"
          "OUT OF SCOPE / INCOMPLETE: none\nWORKERS SPAWNED: 0")
README_MARK = "PROBE-README-LINE-1 readable"
QUOTA_RE = re.compile(r"usage limit|rate limit|too many requests|\b429\b|quota", re.IGNORECASE)


@unittest.skipUnless(os.environ.get("AGENTS_INC_LIVE_BROKER") == "1", "set AGENTS_INC_LIVE_BROKER=1")
class LiveBrokerTest(unittest.TestCase):
    def test_haiku_round_trip(self):
        if not shutil.which("claude"):
            self.skipTest("claude CLI not on PATH")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            cwd = root / "repo"
            cwd.mkdir()
            (cwd / "README.md").write_text(README_MARK + "\n")
            for cmd in (["git", "init", "-q"], ["git", "add", "README.md"],
                        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"]):
                subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)
            run_dir = root / "lead-run"
            run_dir.mkdir()
            (run_dir / "inbox").mkdir()
            (run_dir / "run.json").write_text(json.dumps({
                "schema_version": 1, "run_id": "live-lead", "model": "sol", "effort": "high", "cwd": str(cwd),
                "chain": ["CoS", "sol"], "worker_models": ["haiku"], "permission_mode": "bypassPermissions",
                "fan_out": {"width": 1, "total": 1, "depth": 1}}))
            broker = subprocess.Popen(
                [sys.executable, "-m", "agents_inc.install.cli", "dispatch", "--serve", str(run_dir),
                 "--poll-interval", "1", "--idle-timeout", "600"],
                cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                slots = json.loads(EXAMPLE.read_text())
                # The quoted "$HOME" passes the text screen on purpose: the sandbox must deny it.
                slots["TASK"] = ("Sandbox probe, read-only. Step 1: with the Bash tool run exactly: ls \"$HOME\"/.ssh "
                                 "and keep its first output line, error or not. Step 2: read line 1 of README.md "
                                 "in the current directory. Step 3: reply with exactly the text between the markers, "
                                 "without the markers, replacing SSH_RESULT with the step 1 line and README_LINE with "
                                 "the step 2 line, and nothing else.\n<<<\n" + REPORT + "\n>>>")
                req = {"schema_version": 1, "request_id": "live1", "model": "haiku", "effort": "low",
                       "tier": "grunt", "slots": slots}
                tmp_req = run_dir / "inbox" / "live1.request.json.tmp"
                tmp_req.write_text(json.dumps(req))
                os.rename(tmp_req, run_dir / "inbox" / "live1.request.json")
                # Lead waiter: `agents-inc dispatch --wait` polls once per second, exit 124 after 600 s.
                result_path = run_dir / "live1.result.json"
                waiter = subprocess.run([sys.executable, "-m", "agents_inc.install.cli", "dispatch", "--wait",
                                         str(run_dir), "live1", "--timeout", "600"],
                                        cwd=str(REPO), capture_output=True, text=True)
                print("\nWAITER:", waiter.returncode, waiter.stdout.strip())
                (run_dir / "inbox" / "lead.done").write_text("")
                rc = broker.wait(timeout=30)
            finally:
                if broker.poll() is None:
                    broker.kill()
            _, berr = broker.communicate()
            self.assertTrue(result_path.exists(), "no result within 600 s: exit 124\n" + berr)
            result = json.loads(result_path.read_text())
            report = (run_dir / "live1.report.md").read_text()
            spec = json.loads((run_dir / "run.json").read_text())
            print("\nLIVE RESULT:", json.dumps(result, indent=1))
            print("LIVE REPORT:", report)
            print("LIVE run.json counters:", spec.get("workers_spawned"), spec.get("request_counts"))
            if result["status"] != "green":
                child = run_dir / "workers" / "live1" / "runs" / str(result.get("child_run_id"))
                stderr = (child / "stderr.txt").read_text() if (child / "stderr.txt").is_file() else ""
                if QUOTA_RE.search(stderr + report):
                    self.skipTest("quota exhausted (evidence): " + stderr[-300:])
            self.assertEqual(rc, 0, berr)
            child = run_dir / "workers" / "live1" / "runs" / str(result.get("child_run_id"))
            print("LIVE argv:", json.loads((child / "run.json").read_text()).get("argv", [])[:3])
            self.assertEqual(waiter.returncode, 0, waiter.stderr)
            self.assertEqual(waiter.stdout.strip(), str(result_path))
            if result["status"] != "green":
                tail = (child / "stderr.txt").read_text()[-1500:] if (child / "stderr.txt").is_file() else "<no stderr.txt>"
                verify = (child / "verify.txt").read_text()[-800:] if (child / "verify.txt").is_file() else ""
                self.fail(f"broker result {result['status']} reason={result.get('reason')}\n"
                          f"REPORT:\n{report}\nSTDERR TAIL:\n{tail}\nVERIFY:\n{verify}")
            self.assertEqual(spec["workers_spawned"], 1)
            self.assertIn("Operation not permitted", report)   # sandbox denied ~/.ssh
            self.assertIn(README_MARK, report)                 # cwd read allowed


if __name__ == "__main__":
    unittest.main()
