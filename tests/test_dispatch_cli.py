"""Tests for `agents-inc dispatch` (agents_inc/install/dispatch.py). Writes only to temp dirs."""
from __future__ import annotations
import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents_inc.install import cli, dispatch

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "skills/workerbee/tests/fixtures/example_slots.json"
STATUS_RE = re.compile(r"^dispatch \S+ \S+ rc=-?\d+ report=(COMPLIANT|NON-COMPLIANT:\[.*\]) "
                       r"snapshot=(clean|CHANGED:\S+|ERROR:\S+) outcome=(green|red)( reason=\S+)? out=\S+stdout\.md$")
GOOD_REPORT = ("caveman ultra confirmed. GRILL: none. [verified] gate rc=0 exit code 0.\n"
               "OUT OF SCOPE / INCOMPLETE: none\nWORKERS SPAWNED: 0\n")


def _git_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    for cmd in (["git", "init", "-q"], ["git", "-c", "user.email=t@t", "-c", "user.name=t",
                                        "commit", "-q", "--allow-empty", "-m", "init"]):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)
    return repo


class DispatchCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.repo = _git_repo(self.root)
        self.runs = self.root / "runs"
        # Home without handoff-lint so results do not depend on the host.
        self.env = mock.patch.dict("os.environ", {"HOME": str(self.root)})
        self.env.start()
        self.env_home = mock.patch.dict("os.environ", {}, clear=False)
        self.env_home.start()
        os.environ.pop("AGENTS_INC_HOME_REPO", None)

    def tearDown(self):
        self.env_home.stop()
        self.env.stop()
        self.tmp.cleanup()

    def _slots(self, drop=None, **extra) -> Path:
        data = json.loads(EXAMPLE.read_text())
        if drop:
            data.pop(drop)
        data.update(extra)
        path = self.root / "slots.json"
        path.write_text(json.dumps(data))
        return path

    def _main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(["dispatch", *argv])
        return rc, out.getvalue(), err.getvalue()

    def _run_dir(self) -> Path:
        dirs = list(self.runs.iterdir())
        self.assertEqual(len(dirs), 1)
        return dirs[0]

    def test_argument_parsing(self):
        captured = {}
        with mock.patch.object(dispatch, "run", side_effect=lambda a: captured.setdefault("a", a) and 0):
            self._main("--slots", "s.json", "--model", "sonnet", "--effort", "high", "--cwd", "/x",
                       "--tier", "grunt", "--run-dir", "/r", "--dry-run")
        a = captured["a"]
        self.assertEqual((a.slots, a.model, a.effort, a.cwd, a.tier, a.run_dir, a.dry_run),
                         ("s.json", "sonnet", "high", "/x", "grunt", "/r", True))

    def test_dispatch_cli_rejects_non_grunt_tier(self):
        with mock.patch.object(dispatch, "run") as run, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["dispatch", "--slots", "s.json", "--model", "haiku", "--cwd", "/x", "--tier", "workhorse"])
        self.assertEqual(ctx.exception.code, 2)
        run.assert_not_called()

    def test_render_refusal_missing_out_of_scope(self):
        rc, out, _ = self._main("--slots", str(self._slots(drop="OUT_OF_SCOPE")), "--model", "haiku",
                                "--cwd", str(self.repo), "--run-dir", str(self.runs), "--dry-run")
        self.assertEqual(rc, 3)
        self.assertIn("refused", out)
        self.assertIn("OUT_OF_SCOPE", (self._run_dir() / "lint.txt").read_text())

    def test_lint_refusal_prints_missing(self):
        with mock.patch.object(dispatch, "lint_prompt", return_value=([12], "")):
            rc, out, _ = self._main("--slots", str(self._slots()), "--model", "haiku", "--cwd", str(self.repo),
                                    "--run-dir", str(self.runs))
        self.assertEqual(rc, 3)
        self.assertIn("NON-COMPLIANT:[12]", out)

    def test_dry_run(self):
        rc, out, _ = self._main("--slots", str(self._slots()), "--model", "haiku", "--cwd", str(self.repo),
                                "--run-dir", str(self.runs), "--dry-run")
        self.assertEqual(rc, 0, out)
        run = self._run_dir()
        for name in ("prompt.md", "lint.txt", "snapshot.json", "slots.json", "run.json"):
            self.assertTrue((run / name).is_file(), name)
        self.assertEqual(out.strip(), f"dispatch {run.name} haiku dry-run prompt={run / 'prompt.md'}")
        self.assertTrue((run / "lint.txt").read_text().startswith("COMPLIANT"))

    def _launch(self, model, stdout=GOOD_REPORT, extra=()):
        calls = {}

        def fake(kind, model_, effort, cwd, prompt, run_dir, permission_mode="acceptEdits", resume=None):
            calls.update(kind=kind, model=model_, cwd=cwd, prompt=prompt, permission_mode=permission_mode,
                         effort=effort)
            argv = dispatch.claude_argv(model_, permission_mode, effort=effort) if kind == "claude" else ["run_codex", model_]
            return {"rc": 0, "stdout": stdout, "stderr": "", "argv": argv,
                    "session_id": "sess-1" if kind == "claude" else None}
        with mock.patch.object(dispatch, "launch", side_effect=fake):
            rc, out, _ = self._main("--slots", str(self._slots()), "--model", model, "--cwd", str(self.repo),
                                    "--run-dir", str(self.runs), *extra)
        return rc, out, calls

    def _assert_launched(self, rc, out):
        run = self._run_dir()
        for name in ("stdout.md", "run.json", "verify.txt", "stderr.txt"):
            self.assertTrue((run / name).is_file(), name)
        self.assertRegex(out.strip(), STATUS_RE)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("report=COMPLIANT snapshot=clean", out)
        self.assertEqual(rc, 0, out)
        return json.loads((run / "run.json").read_text())

    def test_launch_codex_mocked(self):
        rc, out, calls = self._launch("sol")
        spec = self._assert_launched(rc, out)
        self.assertEqual(calls["kind"], "codex")
        self.assertEqual(calls["effort"], "medium")
        self.assertEqual(spec["argv"], ["run_codex", "sol"])
        self.assertEqual(spec["effort"], "medium")
        self.assertIsNone(spec["session_id"])

    def test_launch_claude_mocked(self):
        rc, out, calls = self._launch("sonnet")
        spec = self._assert_launched(rc, out)
        self.assertEqual(calls["kind"], "claude")
        self.assertIsNone(calls["effort"])
        argv = spec["argv"]
        self.assertEqual(argv[1:], ["-p", "--model", "claude-sonnet-5-5", "--permission-mode", "acceptEdits",
                                    "--output-format", "json"])
        self.assertIsNone(spec["effort"])
        self.assertNotIn("--effort", argv)
        self.assertEqual(spec["session_id"], "sess-1")
        self.assertIn("SUCCESS GATE", calls["prompt"].upper())

    def test_launch_claude_explicit_effort(self):
        rc, out, calls = self._launch("opus", extra=("--effort", "low"))
        spec = self._assert_launched(rc, out)
        self.assertEqual(calls["effort"], "low")
        self.assertEqual(spec["effort"], "low")
        self.assertEqual(spec["argv"][-2:], ["--effort", "low"])

    def test_fan_out_recorded_in_run_json(self):
        rc, out, _ = self._launch("sonnet")
        spec = self._assert_launched(rc, out)
        self.assertEqual(spec["fan_out"], {"width": 0, "total": 0, "depth": 0})
        self.assertEqual(spec["workers_spawned"], 0)
        self.assertEqual(spec["outcome"], "green")

    def test_workers_over_fan_out_total_is_red(self):
        report = GOOD_REPORT.replace("WORKERS SPAWNED: 0", "WORKERS SPAWNED: 2")
        rc, out, _ = self._launch("sonnet", stdout=report)
        spec = json.loads((self._run_dir() / "run.json").read_text())
        self.assertEqual(spec["workers_spawned"], 2)
        self.assertEqual(spec["outcome"], "red")
        self.assertNotEqual(rc, 0)

    def test_workers_spawned_unknown_is_red_missing(self):
        report = GOOD_REPORT.replace("WORKERS SPAWNED: 0", "WORKERS SPAWNED: unknown")
        rc, out, _ = self._launch("sonnet", stdout=report)
        spec = json.loads((self._run_dir() / "run.json").read_text())
        self.assertEqual(spec["outcome"], "red")
        self.assertEqual(spec["reason"], "workers-spawned-missing")
        self.assertIn("outcome=red reason=workers-spawned-missing", out)
        self.assertNotEqual(rc, 0)

    def test_status_line_green_has_outcome(self):
        rc, out, _ = self._launch("sonnet")
        self.assertIn(" outcome=green out=", out)
        self.assertNotIn("reason=", out)

    def test_over_total_status_has_reason(self):
        report = GOOD_REPORT.replace("WORKERS SPAWNED: 0", "WORKERS SPAWNED: 2")
        _, out, _ = self._launch("sonnet", stdout=report)
        self.assertIn("outcome=red reason=fan-out-over-total", out)

    def test_resume_sums_attempts_against_total(self):
        self._launch("haiku")
        run = self._run_dir()
        path = run / "run.json"
        spec = json.loads(path.read_text())
        spec["fan_out"] = {"width": 3, "total": 6, "depth": 2}
        spec["workers_spawned_attempts"] = [4]
        spec["workers_spawned"] = 4
        path.write_text(json.dumps(spec))
        report = GOOD_REPORT.replace("WORKERS SPAWNED: 0", "WORKERS SPAWNED: 3")

        def fake(*a, **k):
            return {"rc": 0, "stdout": report, "stderr": "", "argv": [], "session_id": "sess-1"}
        with mock.patch.object(dispatch, "launch", side_effect=fake):
            rc, out, _ = self._main("--resume", run.name, "--message", "go", "--run-dir", str(self.runs))
        spec = json.loads(path.read_text())
        self.assertEqual(spec["workers_spawned_attempts"], [4, 3])
        self.assertEqual(spec["workers_spawned"], 7)
        self.assertEqual(spec["outcome"], "red")
        self.assertEqual(spec["reason"], "fan-out-over-total")
        self.assertNotEqual(rc, 0)

    def test_mirror_unset_prints_stderr_line(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err):
            dispatch._mirror({"cwd": "/x/repo", "run_id": "r1"}, self.root, None)
        self.assertEqual(err.getvalue().strip(), "run spec not mirrored: no home repo")

    def test_mirror_copies_run_spec_to_home_repo(self):
        home = self.root / "home"
        home.mkdir()
        fake = lambda *a, **k: {"rc": 0, "stdout": GOOD_REPORT, "stderr": "", "argv": [], "session_id": None}
        with mock.patch.object(dispatch, "launch", side_effect=fake):
            args = argparse.Namespace(slots=str(self._slots()), model="sonnet", effort=None, cwd=str(self.repo),
                                      tier=None, run_dir=str(self.runs), dry_run=False, resume=None,
                                      message=None, home_repo=str(home))
            with contextlib.redirect_stdout(io.StringIO()):
                rc = dispatch.run(args)
        run = self._run_dir()
        dest = home / "specs" / "consumers" / "repo" / "runs" / run.name
        self.assertTrue((dest / "run.json").is_file())
        self.assertTrue((dest / "prompt.md").is_file())

    def test_parse_workers_spawned(self):
        self.assertEqual(dispatch.parse_workers_spawned("x\n- WORKERS SPAWNED: 3\n"), 3)
        self.assertIsNone(dispatch.parse_workers_spawned("no count here"))
        self.assertEqual(dispatch.parse_workers_spawned("[verified] WORKERS SPAWNED: 2.\n"), 2)

    def test_claude_launch_builds_command_and_parses_json(self):
        fake = subprocess.CompletedProcess([], 0, stdout=json.dumps({"result": "hi", "session_id": "s9"}), stderr="")
        with mock.patch.object(dispatch.subprocess, "run", return_value=fake) as run:
            res = dispatch.launch("claude", "opus", "high", self.repo, "PROMPT", self.root, "plan")
        argv = run.call_args.args[0]
        self.assertEqual(argv[1:], ["-p", "--model", dispatch.CLAUDE_MODELS["opus"], "--permission-mode", "plan",
                                    "--output-format", "json", "--effort", "high"])
        self.assertEqual(run.call_args.kwargs["input"], "PROMPT")
        self.assertEqual(run.call_args.kwargs["cwd"], str(self.repo))
        self.assertEqual((res["stdout"], res["session_id"]), ("hi", "s9"))

    def test_unsupported_slug_exits_2(self):
        for slug in ("gemini", "mistral", "openrouter"):
            rc, out, _ = self._main("--slots", str(self._slots()), "--model", slug, "--run-dir", str(self.runs))
            self.assertEqual(rc, 2)
            self.assertEqual(out.strip(), f"dispatch: {slug} not supported, use agent.sh")

    def test_claude_bad_effort_exits_2(self):
        for effort in ("ultra", "xhigh"):
            rc, out, err = self._main("--slots", str(self._slots()), "--model", "haiku", "--effort", effort,
                                      "--cwd", str(self.repo), "--run-dir", str(self.runs))
            self.assertEqual(rc, 2)
            self.assertIn(f"effort {effort} not allowed for haiku", err)
            self.assertFalse(self.runs.exists())

    def test_resume_codex_without_thread_exits_2(self):
        self._launch("terra")
        run = self._run_dir()
        rc, _, err = self._main("--resume", run.name, "--message", "go on", "--run-dir", str(self.runs))
        self.assertEqual(rc, 2)
        self.assertIn("no session id recorded", err)

    def test_resume_codex_uses_thread_id(self):
        self._launch("terra")
        run = self._run_dir()
        spec = json.loads((run / "run.json").read_text())
        spec["session_id"] = "thread-abc"
        (run / "run.json").write_text(json.dumps(spec))
        seen = {}

        def fake(kind, model, effort, cwd, prompt, run_dir, permission_mode="acceptEdits", resume=None):
            seen.update(kind=kind, resume=resume, prompt=prompt, effort=effort)
            return {"rc": 0, "stdout": GOOD_REPORT, "stderr": "", "argv": [], "session_id": "thread-abc"}
        with mock.patch.object(dispatch, "launch", side_effect=fake):
            rc, out, _ = self._main("--resume", run.name, "--message", "go on", "--run-dir", str(self.runs))
        self.assertEqual(rc, 0, out)
        self.assertEqual(seen, {"kind": "codex", "resume": "thread-abc", "prompt": "go on", "effort": "medium"})
        self.assertTrue((run / "stdout.1.md").is_file())
        self.assertTrue((run / "verify.1.txt").is_file())
        self.assertEqual(len(json.loads((run / "run.json").read_text())["resumes"]), 1)

    def test_resume_claude_uses_session(self):
        self._launch("haiku")
        run = self._run_dir()
        seen = {}

        def fake(kind, model, effort, cwd, prompt, run_dir, permission_mode="acceptEdits", resume=None):
            seen.update(resume=resume, prompt=prompt, effort=effort)
            return {"rc": 0, "stdout": GOOD_REPORT, "stderr": "", "argv": [], "session_id": "sess-1"}
        with mock.patch.object(dispatch, "launch", side_effect=fake):
            rc, out, _ = self._main("--resume", run.name, "--message", "go on", "--run-dir", str(self.runs))
        self.assertEqual(rc, 0, out)
        self.assertEqual(seen, {"resume": "sess-1", "prompt": "go on", "effort": None})
        self.assertTrue((run / "stdout.1.md").is_file())

    def test_allow_paths(self):
        self.assertEqual(dispatch.allow_paths("none (read-only scout)"), [])
        self.assertEqual(dispatch.allow_paths("agents_inc/install/cli.py\ntests/test_x.py, README.md"),
                         ["agents_inc/install/cli.py", "tests/test_x.py", "README.md"])


    def test_handoff_lint_findings_are_advisory(self):
        with mock.patch.object(dispatch, "_handoff_lint", return_value=(1, "H2:provenance:L3: finding\n")):
            rc, out, _ = self._main("--slots", str(self._slots()), "--model", "haiku", "--cwd", str(self.repo),
                                    "--run-dir", str(self.runs), "--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("refused", out)
        lint = (self._run_dir() / "lint.txt").read_text()
        self.assertTrue(lint.startswith("COMPLIANT"))
        self.assertIn("advisory", lint)
        self.assertIn("H2:provenance:L3", lint)

    def test_real_snapshot_path_injected_before_lint(self):
        seen = {}
        real_lint = dispatch.lint_prompt

        def spy(path, tier, model=None):
            seen["text"] = path.read_text()
            return real_lint(path, tier, model)

        with mock.patch.object(dispatch, "lint_prompt", side_effect=spy):
            rc, out, _ = self._main("--slots", str(self._slots()), "--model", "haiku", "--cwd", str(self.repo),
                                    "--run-dir", str(self.runs), "--dry-run")
        self.assertEqual(rc, 0, out)
        run = self._run_dir()
        prompt = (run / "prompt.md").read_text()
        snap = str(run / "snapshot.json")
        self.assertIn(f"verify {snap}", prompt)
        self.assertNotIn(dispatch.SNAPSHOT_PLACEHOLDER, prompt)
        self.assertNotIn("/tmp/dispatch/pre_dispatch.json", prompt)
        self.assertEqual(seen["text"], prompt)

    def test_inject_snapshot_appends_when_no_placeholder(self):
        self.assertEqual(dispatch.inject_snapshot("A\n", "/s.json"), "A\nSNAPSHOT: /s.json\n")
        self.assertEqual(dispatch.inject_snapshot("x <snapshot> y <snapshot>", "/s"), "x /s y /s")

    def test_claude_model_ids_exact(self):
        self.assertEqual(dispatch.CLAUDE_MODELS, {
            "fable": "claude-fable-5-1", "opus": "claude-opus-5-5",
            "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-4-5-20251001"})
        self.assertEqual(dispatch.claude_argv("haiku", "plan")[3], "claude-haiku-4-5-20251001")

    def test_claude_argv_effort(self):
        self.assertEqual(dispatch.claude_argv("opus", "plan", effort="low")[-2:], ["--effort", "low"])
        self.assertNotIn("--effort", dispatch.claude_argv("opus", "plan"))
        self.assertEqual(dispatch.claude_argv("opus", "plan", "s1", "max")[-4:],
                         ["--effort", "max", "--resume", "s1"])

if __name__ == "__main__":
    unittest.main()
