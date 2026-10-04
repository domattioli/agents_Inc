import io
import os
import stat
import tempfile
import unittest
from pathlib import Path
import json
import contextlib
from unittest import mock

from agents_inc.install.receipt import InstallReceipt
from agents_inc.install.runtime import MODEL_ALIASES, build_codex_argv, resolve_executable, run_codex


class RuntimeTest(unittest.TestCase):
    def test_aliases_and_isolated_argv(self):
        self.assertEqual(MODEL_ALIASES, {"astra": "gpt-6-astra", "sol": "gpt-6-sol", "terra": "gpt-5.6-terra", "luna": "gpt-5.6-luna"})
        argv = build_codex_argv(Path("/opt/Codex CLI/codex"), "astra", "medium", Path("/work here"), {"gpt-6-astra": ["medium"]})
        self.assertEqual(argv[:4], ["/opt/Codex CLI/codex", "exec", "-m", "gpt-6-astra"])
        self.assertIn("read-only", argv)
        self.assertIn('shell_environment_policy.inherit="none"', argv)
        self.assertIn('web_search="disabled"', argv)
        self.assertIn("features.shell_tool=false", argv)
        self.assertEqual(argv[-1], "-")

    def test_resolution_needs_absolute_executable(self):
        with tempfile.TemporaryDirectory() as raw:
            exe = Path(raw) / "bin" / "codex"
            exe.parent.mkdir(); exe.write_text("#!/bin/sh\n")
            exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
            self.assertEqual(resolve_executable("codex", str(exe.parent)), exe.resolve())
        with self.assertRaises(FileNotFoundError):
            resolve_executable("codex", "")

    def test_unsupported_effort_fails_before_execution(self):
        with self.assertRaises(ValueError):
            build_codex_argv(Path("/x/codex"), "luna", "ultra", Path("/tmp"), {"gpt-5.6-luna": ["low"]})

    def test_bundled_catalog_declares_supported_efforts_for_every_alias(self):
        models = json.loads((Path(__file__).parents[1] / "agents_inc/models.json").read_text())["models"]
        for slug in MODEL_ALIASES.values():
            self.assertIn("supported_efforts", models[slug])
            self.assertIn("medium", models[slug]["supported_efforts"])

    def test_run_codex_quota_error_returns_75(self):
        """Quota error in stderr returns 75 and reports to free_health."""
        with tempfile.TemporaryDirectory() as raw:
            # Create fake codex executable
            fake_codex = Path(raw) / "codex"
            fake_codex.write_text("#!/bin/sh\necho 'ERROR: You have hit your usage limit. Upgrade or try again at 11:26 PM.' >&2\nexit 0\n")
            fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)

            # Create receipt
            receipt = InstallReceipt(
                release_hash="a" * 64,
                python_path=Path("/usr/bin/python3"),
                codex_path=fake_codex
            )

            # Mock free_health.report and capture output
            with mock.patch("agents_inc.free_health.report") as mock_report:
                stdout_capture = io.StringIO()
                stderr_capture = io.StringIO()

                with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tf:
                        tf.write("test")
                        tf.flush()
                        stdin_path = tf.name
                    try:
                        with open(stdin_path) as stdin_file:
                            ret = run_codex("astra", "medium", Path("/tmp"), stdin_file, receipt, {"gpt-6-astra": ["medium"]})
                    finally:
                        os.unlink(stdin_path)

                self.assertEqual(ret, 75)
                stderr_output = stderr_capture.getvalue()
                self.assertIn("retry at 11:26 PM", stderr_output)
                self.assertIn("usage or rate limit", stderr_output)
                mock_report.assert_called_once()
                call_args = mock_report.call_args
                self.assertEqual(call_args[0], ("codex", "gpt-6-astra", "rate_limited"))

    def test_run_codex_empty_output_returns_1(self):
        """Empty stdout with exit 0 returns 1."""
        with tempfile.TemporaryDirectory() as raw:
            # Create fake codex executable that prints nothing
            fake_codex = Path(raw) / "codex"
            fake_codex.write_text("#!/bin/sh\nexit 0\n")
            fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)

            # Create receipt
            receipt = InstallReceipt(
                release_hash="a" * 64,
                python_path=Path("/usr/bin/python3"),
                codex_path=fake_codex
            )

            # Mock free_health.report (should not be called)
            with mock.patch("agents_inc.free_health.report") as mock_report:
                stdout_capture = io.StringIO()
                stderr_capture = io.StringIO()

                with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tf:
                        tf.write("test")
                        tf.flush()
                        stdin_path = tf.name
                    try:
                        with open(stdin_path) as stdin_file:
                            ret = run_codex("astra", "medium", Path("/tmp"), stdin_file, receipt, {"gpt-6-astra": ["medium"]})
                    finally:
                        os.unlink(stdin_path)

                self.assertEqual(ret, 1)
                stderr_output = stderr_capture.getvalue()
                self.assertIn("empty reply", stderr_output)
                mock_report.assert_not_called()

    def test_run_codex_ok_returns_0(self):
        """Normal output with exit 0 returns 0."""
        with tempfile.TemporaryDirectory() as raw:
            # Create fake codex executable that prints to stdout
            fake_codex = Path(raw) / "codex"
            fake_codex.write_text("#!/bin/sh\necho 'REVIEW-OK'\nexit 0\n")
            fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)

            # Create receipt
            receipt = InstallReceipt(
                release_hash="a" * 64,
                python_path=Path("/usr/bin/python3"),
                codex_path=fake_codex
            )

            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()

            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as tf:
                    tf.write("test")
                    tf.flush()
                    stdin_path = tf.name
                try:
                    with open(stdin_path) as stdin_file:
                        ret = run_codex("astra", "medium", Path("/tmp"), stdin_file, receipt, {"gpt-6-astra": ["medium"]})
                finally:
                    os.unlink(stdin_path)

            self.assertEqual(ret, 0)
            stdout_output = stdout_capture.getvalue()
            self.assertIn("REVIEW-OK", stdout_output)

    def test_run_codex_passthrough_exit_code(self):
        """Non-zero exit code is returned as-is."""
        with tempfile.TemporaryDirectory() as raw:
            # Create fake codex executable that exits with 3
            fake_codex = Path(raw) / "codex"
            fake_codex.write_text("#!/bin/sh\necho 'x'\nexit 3\n")
            fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)

            # Create receipt
            receipt = InstallReceipt(
                release_hash="a" * 64,
                python_path=Path("/usr/bin/python3"),
                codex_path=fake_codex
            )

            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()

            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as tf:
                    tf.write("test")
                    tf.flush()
                    stdin_path = tf.name
                try:
                    with open(stdin_path) as stdin_file:
                        ret = run_codex("astra", "medium", Path("/tmp"), stdin_file, receipt, {"gpt-6-astra": ["medium"]})
                finally:
                    os.unlink(stdin_path)

            self.assertEqual(ret, 3)
            stdout_output = stdout_capture.getvalue()
            self.assertIn("x", stdout_output)

    def test_run_codex_no_false_positive_on_non_error_lines(self):
        """Strings like '429' and 'rate limit' outside ERROR lines do not trigger quota detection."""
        with tempfile.TemporaryDirectory() as raw:
            # Create fake codex executable that mentions "429" and "rate limit" in non-ERROR output
            fake_codex = Path(raw) / "codex"
            fake_codex.write_text("#!/bin/sh\necho 'user: please review this rate limit code; status 429' >&2\necho 'tokens used 14,290' >&2\necho 'REVIEW-OK'\nexit 0\n")
            fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)

            # Create receipt
            receipt = InstallReceipt(
                release_hash="a" * 64,
                python_path=Path("/usr/bin/python3"),
                codex_path=fake_codex
            )

            # Ensure free_health.report is not called
            with mock.patch("agents_inc.free_health.report") as mock_report:
                stdout_capture = io.StringIO()
                stderr_capture = io.StringIO()

                with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tf:
                        tf.write("test")
                        tf.flush()
                        stdin_path = tf.name
                    try:
                        with open(stdin_path) as stdin_file:
                            ret = run_codex("astra", "medium", Path("/tmp"), stdin_file, receipt, {"gpt-6-astra": ["medium"]})
                    finally:
                        os.unlink(stdin_path)

                self.assertEqual(ret, 0)
                stdout_output = stdout_capture.getvalue()
                self.assertIn("REVIEW-OK", stdout_output)
                mock_report.assert_not_called()
