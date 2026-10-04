"""D51 live proof: a terra Lead calls the `dispatch` MCP tool once for one real haiku Worker.

At most 2 attempts, retried only on reason report-noncompliant or when Codex never loaded the dispatch tool; any other outcome fails on attempt 1.

Run: AGENTS_INC_LIVE_MCP=1 python3 -m unittest tests.test_mcp_broker_live
Skipped unless AGENTS_INC_LIVE_MCP=1. Launches one terra and one haiku. Quota exhaustion skips with evidence.
"""
from __future__ import annotations
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agents_inc.install import cli, runtime

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "skills/workerbee/tests/fixtures/example_slots.json"
README_MARK = "PROBE-README-LINE-1 readable"
REPORT = ("caveman NOT installed -> checked by hand. GRILL: none. [verified] gate rc=0 exit code 0.\n"
          "README_PROBE: README_LINE\nOUT OF SCOPE / INCOMPLETE: none\nWORKERS SPAWNED: 0")
QUOTA_RE = re.compile(r"usage limit|rate limit|too many requests|\b429\b|quota", re.IGNORECASE)
CODEX = shutil.which("codex") and Path(shutil.which("codex")).resolve()


@unittest.skipUnless(os.environ.get("AGENTS_INC_LIVE_MCP") == "1", "set AGENTS_INC_LIVE_MCP=1")
class LiveMcpTest(unittest.TestCase):
    def test_terra_lead_dispatches_haiku(self):
        if not shutil.which("claude") or not CODEX:
            self.skipTest("claude or codex CLI not on PATH")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            cwd = root / "repo"
            cwd.mkdir()
            (cwd / "README.md").write_text(README_MARK + "\n")
            for cmd in (["git", "init", "-q"], ["git", "add", "README.md"],
                        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"]):
                subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)
            slots = json.loads(EXAMPLE.read_text())
            slots["TASK"] = ("Read-only probe. Read line 1 of README.md in the current directory, then reply with the "
                             "following four lines verbatim as plain text, not inside a code fence, with README_LINE "
                             "replaced by line 1 of README.md:\n" + REPORT)
            slots["SUCCESS_GATE"] = "`head -1 README.md` prints the line you returned."
            slots["FAILURE_GATE"] = "`head -1 README.md` differs from the returned line, report RED."
            slots["PRE_EXISTING_CHANGES"] = "none: read-only probe, no writes."
            def make_prompt(run_dir):
                return ("First, with the shell tool run exactly: ls \"" + str(run_dir) + "\" and keep its output, error or not. "
                        "The `agents_inc` MCP server is connected. Its tools are lazy-loaded: call `tool_search` with "
                        "query \"agents_inc\", which returns `mcp__agents_inc__dispatch`, `mcp__agents_inc__status` and "
                        "`mcp__agents_inc__wait`. Then call `mcp__agents_inc__dispatch` exactly once with these arguments: "
                        f"model \"haiku\", effort \"low\", slots equal to this JSON object:\n{json.dumps(slots)}\n"
                        "Do not call any other tool except at most one `status`. Then reply with the `ls` output line, the "
                        "tool's `status` and `outcome` fields and the report text, nothing else.")
            efforts = cli._efforts(REPO)
            for attempt in (1, 2):  # retry only haiku wording variance: reason report-noncompliant
                run_dir = root / f"lead-run-{attempt}"
                run_dir.mkdir()  # no inbox: the Lead has no write grant in MCP mode
                (run_dir / "run.json").write_text(json.dumps({
                    "schema_version": 1, "run_id": "live-mcp", "model": "terra", "effort": "high", "cwd": str(cwd),
                    "chain": ["CoS", "terra"], "worker_models": ["haiku"], "permission_mode": "bypassPermissions",
                    "fan_out": {"width": 1, "total": 1, "depth": 1}}))
                out, err = io.StringIO(), io.StringIO()
                with tempfile.TemporaryFile("w+") as stdin:
                    stdin.write(make_prompt(run_dir))
                    stdin.seek(0)
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        rc = runtime.run_codex("terra", "medium", cwd, stdin, SimpleNamespace(codex_path=CODEX), efforts,
                                               lead_dir=run_dir)
                text = out.getvalue() + err.getvalue()
                print(f"\nATTEMPT {attempt} LEAD rc:", rc, "\nLEAD OUTPUT TAIL:", text[-2500:], file=sys.stderr)
                if rc == 75 or (rc != 0 and QUOTA_RE.search(text)):
                    self.skipTest("quota exhausted (evidence): " + text[-300:])
                spec = json.loads((run_dir / "run.json").read_text())
                log = (run_dir / "mcp.log").read_text() if (run_dir / "mcp.log").is_file() else ""
                print("MCP LOG:\n" + log, file=sys.stderr)
                print("run.json counters:", spec.get("workers_spawned"), spec.get("request_counts"), file=sys.stderr)
                results = sorted(run_dir.glob("mcp-*.result.json"))
                noncompliant = (len(results) == 1 and
                                json.loads(results[0].read_text()).get("reason") == "report-noncompliant")
                never_loaded = not results and "mcp: agents_inc/dispatch" not in text  # Codex-side startup flake
                if (noncompliant or never_loaded) and attempt == 1:
                    continue
                break
            self.assertIn('"transport": "mcp"', text)
            self.assertIn("Operation not permitted", text)  # the Lead's shell cannot read the broker run directory
            self.assertRegex(log, r"env-keys: [^\n]*\bCODEX_HOME\b")  # reached the MCP server via the env table
            results = sorted(run_dir.glob("mcp-*.result.json"))
            self.assertEqual(len(results), 1, f"attempt {attempt}: no result file; log:\n" + log)
            result = json.loads(results[0].read_text())
            print("RESULT:", json.dumps(result, indent=1), file=sys.stderr)
            self.assertEqual(result["status"], "green", f"attempt {attempt}: {result}")
            self.assertEqual(spec["workers_spawned"], 1)
            self.assertIn("README_PROBE: " + README_MARK, Path(result["report_path"]).read_text())
            self.assertIn("tool=dispatch ok", log)


if __name__ == "__main__":
    unittest.main()
