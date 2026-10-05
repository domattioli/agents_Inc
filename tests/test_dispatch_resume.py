"""D54: Codex session capture and resume, Claude effort argv, delegate write path, home repo resolution."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from agents_inc.install import cli, dispatch, runtime

MAP = {"terra": "gpt-5.6-terra", "luna": "gpt-5.6-luna"}
EFF = {slug: ["low", "medium"] for slug in MAP.values()}
EXE = Path("/x/codex")
THREAD = "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"
# Shape of `codex exec --json` output: one JSON event per line.
JSONL = "\n".join([
    json.dumps({"type": "thread.started", "thread_id": THREAD}),
    json.dumps({"type": "turn.started"}),
    json.dumps({"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "hello"}}),
    json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}),
]) + "\n"


class ResumeArgvTest(unittest.TestCase):
    def test_resume_argv_shape(self):
        argv = runtime.build_codex_resume_argv(EXE, THREAD, "go on", "luna", "low", Path("/w"), EFF, MAP,
                                               json_out=Path("/t/last.md"))
        self.assertEqual(argv[:4], [str(EXE), "exec", "resume", THREAD])
        self.assertEqual(argv[-1], "go on")
        self.assertNotIn("-C", argv)
        self.assertNotIn("-s", argv)
        self.assertNotIn("-", argv)
        self.assertIn("--skip-git-repo-check", argv)
        self.assertEqual(argv[argv.index("-m") + 1], "gpt-5.6-luna")
        self.assertIn("model_reasoning_effort=low", argv)
        self.assertIn('sandbox_mode="read-only"', argv)
        self.assertIn("features.shell_tool=false", argv)
        self.assertEqual(argv[argv.index("-o") + 1], "/t/last.md")
        self.assertIn("--json", argv)

    def test_resume_argv_keeps_permission_profile_and_worker_server(self):
        argv = runtime.build_codex_resume_argv(EXE, THREAD, "-x starts with a dash", "terra", "medium", Path("/w"),
                                               EFF, MAP, tools=True, extra_deny=(Path("/deny"),),
                                               worker=(Path("/c/ask"), "r1", Path("/c/worker_mcp.py")))
        joined = " ".join(argv)
        self.assertIn(f'default_permissions="{runtime.PROFILE}"', argv)
        self.assertIn('"/deny"="none"', joined)
        self.assertIn("mcp_servers.agents_inc.command=", joined)
        self.assertIn('"--request-id", "r1"', joined)
        self.assertEqual(argv[-1], " -x starts with a dash")

    def test_resume_argv_refuses_bad_thread_id(self):
        for bad in ("", "-rf", "a b", "x" * 200, None):
            with self.assertRaises(ValueError):
                runtime.build_codex_resume_argv(EXE, bad, "m", "luna", "low", Path("/w"), EFF, MAP)


class ThreadParseTest(unittest.TestCase):
    def test_parse_thread_id_from_jsonl(self):
        self.assertEqual(runtime.parse_thread_id(JSONL), THREAD)
        self.assertIsNone(runtime.parse_thread_id("not json\n{}\n"))
        self.assertIsNone(runtime.parse_thread_id(json.dumps({"type": "thread.started", "thread_id": "-bad"})))

    def test_json_errors_reported(self):
        text = JSONL + json.dumps({"type": "turn.failed", "error": {"message": "usage limit reached"}}) + "\n"
        self.assertEqual(runtime._json_errors(text), ["ERROR: usage limit reached"])


class _CodexStub:
    """subprocess.run stand-in for Codex: writes the -o file and prints JSONL, like `codex exec --json -o`."""

    def __init__(self, reply="REPORT\n", thread=THREAD):
        self.calls, self.reply, self.thread = [], reply, thread

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        Path(argv[argv.index("-o") + 1]).write_text(self.reply)
        events = json.dumps({"type": "thread.started", "thread_id": self.thread}) + "\n"
        return SimpleNamespace(stdout=events, stderr="", returncode=0)


class RunCodexJsonTest(unittest.TestCase):
    def _run(self, stub, **kw):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(runtime, "load_model_map", return_value=MAP), \
                mock.patch.object(runtime.subprocess, "run", side_effect=stub), \
                mock.patch.object(runtime.os, "access", return_value=True), \
                mock.patch.object(runtime.Path, "is_file", return_value=True), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = runtime.run_codex("luna", "low", Path("/w"), io.StringIO("the prompt"),
                                   SimpleNamespace(codex_path="/x/codex"), EFF, **kw)
        return rc, out.getvalue(), err.getvalue()

    def test_thread_out_records_id_and_prints_last_message(self):
        stub, thread = _CodexStub(), {}
        rc, out, err = self._run(stub, thread_out=thread)
        self.assertEqual(rc, 0, err)
        self.assertEqual(thread, {"thread_id": THREAD})
        self.assertEqual(out, "REPORT\n")
        argv, kw = stub.calls[0]
        self.assertEqual(argv[-1], "-")
        self.assertEqual(kw["input"], "the prompt")
        self.assertFalse(Path(argv[argv.index("-o") + 1]).parent.exists())  # temp dir removed

    def test_resume_thread_passes_message_positional_and_cwd(self):
        stub = _CodexStub(reply="SECOND\n")
        rc, out, err = self._run(stub, resume_thread=THREAD)
        self.assertEqual(rc, 0, err)
        argv, kw = stub.calls[0]
        self.assertEqual(argv[1:4], ["exec", "resume", THREAD])
        self.assertEqual(argv[-1], "the prompt")
        self.assertEqual((kw["input"], kw["cwd"]), ("", "/w"))
        self.assertEqual(out, "SECOND\n")

    def test_resume_refused_for_lead(self):
        with self.assertRaises(ValueError):
            self._run(_CodexStub(), resume_thread=THREAD, lead_dir=Path("/nonexistent"))


class FakeCodexScriptTest(unittest.TestCase):
    """A real child process: a shell script that answers like `codex exec [resume] --json -o FILE`."""

    def test_launch_then_resume_with_fake_codex(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            log = root / "calls.log"
            exe = root / "codex"
            exe.write_text(
                "#!/bin/sh\n"
                f'echo "$*" >> "{log}"\n'
                'out=""; prev=""\n'
                'for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done\n'
                'if [ "$2" = "resume" ]; then\n'
                '  for last in "$@"; do :; done\n'
                '  printf "resumed %s with: %s\\n" "$3" "$last" > "$out"\n'
                'else\n'
                '  cat > /dev/null; printf "first turn\\n" > "$out"\n'
                'fi\n'
                f'echo \'{{"type":"thread.started","thread_id":"{THREAD}"}}\'\n')
            exe.chmod(0o755)
            receipt = SimpleNamespace(codex_path=str(exe))
            paths = SimpleNamespace(receipt=root / "r.json", current=root)
            with mock.patch.object(cli, "_paths", return_value=paths), \
                    mock.patch.object(cli, "_efforts", return_value=EFF), \
                    mock.patch("agents_inc.install.receipt.InstallReceipt.load", return_value=receipt), \
                    mock.patch.object(runtime, "load_model_map", return_value=MAP):
                first = dispatch.launch("codex", "luna", "low", root, "hello", root)
                second = dispatch.launch("codex", "luna", "low", root, "and now?", root, resume=first["session_id"])
            self.assertEqual(first["session_id"], THREAD)
            self.assertEqual(first["stdout"], "first turn\n")
            self.assertEqual(second["stdout"], f"resumed {THREAD} with: and now?\n")
            self.assertEqual(second["session_id"], THREAD)
            self.assertEqual(second["argv"][-2:], ["resume", THREAD])
            calls = log.read_text().splitlines()
            self.assertTrue(calls[1].startswith(f"exec resume {THREAD} "))


class ClaudeEffortTest(unittest.TestCase):
    def test_claude_effort_argv(self):
        argv = dispatch.claude_argv("haiku", "default", resume="s1", effort="high")
        self.assertEqual(argv[argv.index("--effort") + 1], "high")
        self.assertEqual(argv[argv.index("--resume") + 1], "s1")
        self.assertNotIn("--effort", dispatch.claude_argv("haiku", "default"))


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class DefaultParentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.env = mock.patch.dict(os.environ, {"TMPDIR": str(self.root / "tmpdir")})
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop("CLAUDE_SCRATCHPAD", None)

    def _repo(self, name: str, ignore: bool, scratch: bool = True) -> Path:
        repo = self.root / name
        repo.mkdir()
        _git(repo, "init", "-q")
        if ignore:
            (repo / ".gitignore").write_text(".scratch/\n")
        if scratch:
            (repo / ".scratch").mkdir()
        return repo

    def test_ignored_scratch_preferred(self):
        repo = self._repo("a", ignore=True)
        self.assertEqual(dispatch.default_parent(repo), repo / ".scratch" / "agents-inc-runs")

    def test_tracked_scratch_falls_back(self):
        repo = self._repo("b", ignore=False)
        self.assertEqual(dispatch.default_parent(repo), self.root / "tmpdir" / "agents-inc-runs")

    def test_missing_scratch_and_non_repo_fall_back(self):
        repo = self._repo("c", ignore=True, scratch=False)
        self.assertEqual(dispatch.default_parent(repo), self.root / "tmpdir" / "agents-inc-runs")
        plain = self.root / "plain"
        (plain / ".scratch").mkdir(parents=True)
        self.assertEqual(dispatch.default_parent(plain), self.root / "tmpdir" / "agents-inc-runs")
        self.assertEqual(dispatch.default_parent(None), self.root / "tmpdir" / "agents-inc-runs")


class HomeRepoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.env = mock.patch.dict(os.environ, {"HOME": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop("AGENTS_INC_HOME_REPO", None)

    def test_resolution_order(self):
        (self.root / "AGENTS.md").write_text("# x\n\nagents-inc home repo: ~/Projects/DomI\n"
                                             "agents-inc home repo: /second\n")
        self.assertEqual(dispatch.resolve_home_repo(None, self.root), str(self.root / "Projects/DomI"))
        with mock.patch.dict(os.environ, {"AGENTS_INC_HOME_REPO": "/from/env"}):
            self.assertEqual(dispatch.resolve_home_repo(None, self.root), "/from/env")
            self.assertEqual(dispatch.resolve_home_repo("/from/flag", self.root), "/from/flag")

    def test_no_agents_md_or_no_line(self):
        self.assertIsNone(dispatch.resolve_home_repo(None, self.root))
        (self.root / "AGENTS.md").write_text("no pointer here\n")
        self.assertIsNone(dispatch.resolve_home_repo(None, self.root))


if __name__ == "__main__":
    unittest.main()
