"""`agents-inc run --thread FILE`: one Codex thread per file, live event and usage lines on stderr."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents_inc.install.receipt import InstallReceipt
from agents_inc.install.runtime import run_codex_thread

FAKE = """#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
stdin = sys.stdin.read()
with open(os.environ["FAKE_ARGV_LOG"], "a") as f:
    f.write(json.dumps({"argv": argv, "stdin": stdin}) + "\\n")
with open(argv[argv.index("-o") + 1], "w") as f:
    f.write("last message\\n")
tid = argv[argv.index("resume") + 1] if "resume" in argv else "thread-new-1"
for event in (
    {"type": "thread.started", "thread_id": tid},
    {"type": "item.completed", "item": {"type": "reasoning", "text": "thinking it over"}},
    {"type": "item.completed", "item": {"type": "command_execution", "command": "ls"}},
    {"type": "item.completed", "item": {"type": "agent_message", "text": "last message"}},
    {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 3}},
):
    print(json.dumps(event), flush=True)
sys.exit(int(os.environ.get("FAKE_RC", "0")))
"""


class RunThreadTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        fake = self.dir / "codex"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        self.receipt = InstallReceipt(release_hash="a" * 64, python_path=Path("/usr/bin/python3"), codex_path=fake)
        self.log = self.dir / "argv.jsonl"
        env = mock.patch.dict(os.environ, {"FAKE_ARGV_LOG": str(self.log)})
        env.start()
        self.addCleanup(env.stop)

    def run_thread(self, thread_file, message="hello"):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = run_codex_thread(thread_file, "astra", "medium", self.dir, io.StringIO(message), self.receipt,
                                  {"gpt-6-astra": ["medium"]}, no_tools=True)
        return rc, out.getvalue(), err.getvalue()

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_new_thread_writes_file_and_makes_parents(self):
        thread = self.dir / "sub" / "dir" / "a.thread"
        rc, out, _ = self.run_thread(thread)
        self.assertEqual(rc, 0)
        self.assertEqual(thread.read_text().strip(), "thread-new-1")
        argv = self.calls()[0]["argv"]
        self.assertNotIn("resume", argv)
        self.assertIn("--json", argv)
        self.assertEqual(self.calls()[0]["stdin"], "hello")

    def test_empty_file_starts_a_new_thread(self):
        thread = self.dir / "a.thread"
        thread.write_text("\n")
        self.run_thread(thread)
        self.assertNotIn("resume", self.calls()[0]["argv"])
        self.assertEqual(thread.read_text().strip(), "thread-new-1")

    def test_file_with_id_resumes(self):
        thread = self.dir / "a.thread"
        thread.write_text("thread-old-7\n")
        rc, out, _ = self.run_thread(thread, "next message")
        self.assertEqual(rc, 0)
        argv = self.calls()[0]["argv"]
        self.assertIn("resume", argv)
        self.assertIn("thread-old-7", argv)
        self.assertEqual(argv[-1], "next message")  # the message rides the PROMPT positional
        self.assertEqual(thread.read_text().strip(), "thread-old-7")

    def test_event_and_usage_lines_on_stderr_in_order(self):
        _, _, err = self.run_thread(self.dir / "a.thread")
        lines = [l for l in err.splitlines() if l.startswith("agents-inc run: ")]
        kinds = [l.split(" ")[2] for l in lines]
        self.assertEqual(kinds, ["record", "event", "event", "usage"])
        self.assertEqual(json.loads(lines[1].split(" event ", 1)[1]), {"kind": "reasoning", "text": "thinking it over"})
        self.assertEqual(json.loads(lines[2].split(" event ", 1)[1]), {"kind": "agent_message", "text": "last message"})
        self.assertEqual(json.loads(lines[3].split(" usage ", 1)[1]),
                         {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 3})

    def test_stdout_is_the_last_message_only(self):
        _, out, _ = self.run_thread(self.dir / "a.thread")
        self.assertEqual(out, "last message\n")

    def test_failed_new_run_writes_no_file(self):
        thread = self.dir / "a.thread"
        with mock.patch.dict(os.environ, {"FAKE_RC": "3"}):
            rc, _, _ = self.run_thread(thread)
        self.assertEqual(rc, 3)
        self.assertEqual(thread.read_text().strip(), "thread-new-1")  # the id still arrived on thread.started


class RunThreadCliTest(unittest.TestCase):
    def test_thread_with_lead_is_rejected(self):
        from agents_inc.install import cli
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as raw, contextlib.redirect_stderr(err), \
                mock.patch.object(cli, "InstallReceipt") as receipt:
            receipt.load.return_value = object()
            with mock.patch("pathlib.Path.exists", return_value=True):
                rc = cli.main(["run", "--model", "astra", "--cwd", raw, "--thread", f"{raw}/t", "--lead", f"{raw}/lead"])
        self.assertEqual(rc, 2)
        self.assertIn("--thread cannot be combined with --lead", err.getvalue())


if __name__ == "__main__":
    unittest.main()
