"""`agents-inc report`: preview by default, redaction, secret refusal, gh filing."""
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents_inc.install import report


class ReportTest(unittest.TestCase):
    def test_draft_shape_and_redaction(self):
        t, label, body = report.draft("bug", "dispatch hangs in /Users/x/p", "trace at /Users/x/p/f.py", "ENV", home="/Users/x")
        self.assertEqual((t, label), ("[bug] dispatch hangs in ~/p", "bug"))
        self.assertIn("## What happened\n\ntrace at ~/p/f.py", body)
        self.assertIn("## Environment\n\nENV", body)
        self.assertNotIn("/Users/x", body)
        self.assertEqual(report.draft("feature", "t", "b", "E")[1], "enhancement")

    def test_refuses_secret_and_empty(self):
        for body in ("key sk-abcdefghijklmnopqrstuv", "ghp_" + "a" * 30, "api_key = hunter2hunter2"):
            with self.assertRaisesRegex(ValueError, "secret"):
                report.draft("bug", "t", body, "E")
        with self.assertRaisesRegex(ValueError, "required"):
            report.draft("bug", " ", "b", "E")

    def _run(self, submit, rc=0):
        calls, lines = [], []

        def runner(argv, **kw):
            calls.append((argv, kw))
            if "--version" in argv:
                return subprocess.CompletedProcess(argv, 0, stdout="codex-cli 9\n", stderr="")
            return subprocess.CompletedProcess(argv, rc, stdout="https://github.com/o/r/issues/9\n", stderr="boom")
        with mock.patch.object(report.shutil, "which", side_effect=lambda n: f"/bin/{n}"):
            code = report.run("bug", "t", "b", submit, ["READY"], runner=runner, out=lines.append)
        return code, calls, "\n".join(lines)

    def test_preview_files_nothing(self):
        code, calls, text = self._run(False)
        self.assertEqual(code, 0)
        self.assertFalse(any("issue" in c[0] for c in calls))
        self.assertIn("not filed", text)
        self.assertIn("codex-cli 9", text)

    def test_submit_calls_gh(self):
        code, calls, text = self._run(True)
        self.assertEqual(code, 0)
        argv, kw = calls[-1]
        self.assertEqual(argv[:5], ["/bin/gh", "issue", "create", "--repo", report.REPO])
        self.assertIn("[bug] t", argv)
        self.assertIn("## What happened", kw["input"])
        self.assertIn("filed: https://github.com/o/r/issues/9", text)
        self.assertEqual(self._run(True, rc=1)[0], 1)


if __name__ == "__main__":
    unittest.main()
