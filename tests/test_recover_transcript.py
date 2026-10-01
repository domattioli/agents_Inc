"""Spec 015 (#13): bounded recovery summary of a stopped delegate's transcript.

Supervisor-owned acceptance tests. Generated fixture transcripts only; never reads ~/.claude/projects.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "workerbee" / "scripts" / "recover_transcript.py"


def assistant(blocks, stop_reason=None):
    return {"type": "assistant", "message": {"role": "assistant", "content": blocks, "stop_reason": stop_reason}}


def tool_use(name, **inp):
    return {"type": "tool_use", "id": f"tu-{name}", "name": name, "input": inp}


def tool_result(text, is_error=False):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "x", "content": text, "is_error": is_error}]}}


class RecoverTranscriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rows, extra_lines=()):
        path = self.dir / "t.jsonl"
        with path.open("w") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
            for line in extra_lines:
                fh.write(line + "\n")
        return path

    def run_script(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, timeout=60)

    def test_summary_lists_written_files_last_text_and_error(self):
        path = self.write([
            assistant([tool_use("Write", file_path="/repo/a.py", content="x")]),
            assistant([tool_use("Edit", file_path="/repo/b.py", old_string="a", new_string="b")]),
            assistant([tool_use("NotebookEdit", notebook_path="/repo/c.ipynb", new_source="x")]),
            tool_result("Exit code 1\nboom failure", is_error=True),
            assistant([{"type": "text", "text": "Final words of the delegate."}], stop_reason="end_turn"),
        ])
        proc = self.run_script(path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for needle in ("/repo/a.py", "/repo/b.py", "/repo/c.ipynb", "Final words of the delegate.", "boom failure"):
            self.assertIn(needle, proc.stdout)
        self.assertLessEqual(len(proc.stdout), 4000)

    # SC-002: a 5 MB transcript stays within the bound and still lists the written files
    def test_large_transcript_output_is_bounded(self):
        filler = "lorem ipsum " * 400
        rows = [assistant([{"type": "text", "text": filler}]) for _ in range(1100)]
        rows.insert(10, assistant([tool_use("Write", file_path="/repo/early.py", content="x")]))
        rows.append(assistant([tool_use("Edit", file_path="/repo/late.py", old_string="a", new_string="b")]))
        rows.append(assistant([{"type": "text", "text": filler * 3}], stop_reason="end_turn"))
        path = self.write(rows)
        self.assertGreater(path.stat().st_size, 5_000_000)
        proc = self.run_script(path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertLessEqual(len(proc.stdout), 4000)
        self.assertIn("/repo/early.py", proc.stdout)
        self.assertIn("/repo/late.py", proc.stdout)

    def test_custom_bound_is_respected(self):
        path = self.write([assistant([{"type": "text", "text": "y" * 5000}], stop_reason="end_turn")])
        proc = self.run_script(path, "--max-chars", "1000")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertLessEqual(len(proc.stdout), 1000)

    def test_malformed_lines_are_skipped_and_counted(self):
        path = self.write([assistant([{"type": "text", "text": "ok"}], stop_reason="end_turn")],
                          extra_lines=("{not json", "", "[1, 2"))
        proc = self.run_script(path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertRegex(proc.stdout, r"(?i)skipped[^0-9\n]*2\b")

    def test_handback_marks_status(self):
        path = self.write([assistant([tool_use("SubagentHandback", message="report body")])])
        proc = self.run_script(path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("handback", proc.stdout.lower())

    def test_missing_transcript_exits_nonzero_with_message(self):
        proc = self.run_script(self.dir / "absent.jsonl")
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(proc.stderr.strip())


if __name__ == "__main__":
    unittest.main()
