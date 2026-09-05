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

    def test_codex_cmd_has_isolated_cwd_and_no_env(self):
        cmd = codex.build_cmd("gpt-5.4-mini", cwd="/tmp/x")
        self.assertIn("-C", cmd); self.assertEqual(cmd[cmd.index("-C")+1], "/tmp/x")
        self.assertIn('shell_environment_policy.inherit="none"', cmd)
        self.assertIn('web_search="disabled"', cmd)
        self.assertIn("features.shell_tool=false", cmd)
        self.assertNotIn("tools.web_search=false", cmd)

    def test_run_worker_accepts_cwd(self):
        import tempfile
        d = tempfile.mkdtemp()
        r = run_worker(["pwd"], "", cwd=d)
        self.assertTrue(r.output.strip().endswith(d.split("/")[-1]))
