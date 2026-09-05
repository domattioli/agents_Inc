# tests/test_adapters.py
import unittest
from workerbees.adapters import claude, codex
from workerbees.adapters.base import run_worker

DISALLOWED = {"Bash","PowerShell","Read","Edit","Write","Glob","Grep","Task",
              "AskUserQuestion","TodoWrite","WebFetch","WebSearch","NotebookEdit"}

class AdapterTest(unittest.TestCase):
    def test_claude_cmd_is_tool_free_and_not_bare(self):
        cmd = claude.build_cmd("haiku")
        self.assertNotIn("--bare", cmd)
        self.assertIn("--strict-mcp-config", cmd)
        i = cmd.index("--disallowedTools")
        self.assertTrue(DISALLOWED.issubset(set(cmd[i+1:-1])))  # exclude the trailing "--"
        self.assertEqual(cmd[-1], "--")  # last element must be "--"
        self.assertNotIn("hi", cmd)  # prompt must not be in command
        self.assertEqual(cmd[cmd.index("--setting-sources")+1], "")

    def test_codex_cmd_read_only_stdin(self):
        cmd = codex.build_cmd("gpt-5.4-mini")
        self.assertEqual(cmd[:2], ["codex", "exec"])
        self.assertIn("read-only", cmd)
        self.assertEqual(cmd[-1], "-")

    def test_run_worker_exit0_is_returned_not_verified(self):
        r = run_worker(["cat"], "echo-me")
        self.assertEqual((r.status, r.output.strip()), ("returned", "echo-me"))

    def test_run_worker_quota_pattern_pauses(self):
        r = run_worker(["sh", "-c", "echo 'rate limit exceeded' >&2; exit 1"], "")
        self.assertEqual(r.status, "paused")
