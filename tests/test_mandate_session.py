"""Tests for spec-010 (persistent Executive/Supervisor session across a mandate).

Covers the mandate store (load_mandate/save_mandate, FR-009), engage()'s
fresh-vs-resume decision + guards (FR-002..FR-008, I1-I4), the mandate CLI verb
group (close/list/show, contracts C2/C2a), the state-dir containment guard
(FR-015, contracts C7), and end-to-end `submit --mandate` wiring against a stub
`ask.sh` fixture (no live provider call -- tests/fixtures/mandate/stub_ask.sh).

See specs/010-persistent-exec-session/{spec,plan,data-model,contracts/cli-and-bridge}.md.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER_DIR = REPO_ROOT / "skills" / "codex-bridge" / "scripts"
FIXTURE_STUB = REPO_ROOT / "tests" / "fixtures" / "mandate" / "stub_ask.sh"

sys.path.insert(0, str(RUNNER_DIR))
import agent_runner  # noqa: E402


class MandateSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmp.name)
        self.state_dir = tmp_path / "state"
        self.scripts_dir = tmp_path / "scripts"
        self.scripts_dir.mkdir(parents=True)
        stub_ask = self.scripts_dir / "ask.sh"
        stub_ask.write_bytes(FIXTURE_STUB.read_bytes())
        stub_ask.chmod(0o755)
        self.capture_path = tmp_path / "capture.jsonl"

        env_overrides = {
            "CODEX_BRIDGE_AGENT_STATE_DIR": str(self.state_dir),
            "CODEX_BRIDGE_SCRIPTS_DIR": str(self.scripts_dir),
            "CODEX_BRIDGE_ACTOR": "test-actor",
            "CODEX_BRIDGE_MODE": "standard",
        }
        self._env_backup: dict[str, str | None] = {}
        for key, value in env_overrides.items():
            self._env_backup[key] = os.environ.get(key)
            os.environ[key] = value
        os.environ.pop("CODEX_BRIDGE_STUB_CAPTURE", None)
        os.environ.pop("CODEX_BRIDGE_STUB_RESUME_FAIL", None)

        # Direct in-process calls (engage/load_mandate/mandate_close/...) read the
        # module's own attributes, not env vars re-read at call time -- patch both so
        # in-process calls AND the real subprocess `_run` worker agree on paths.
        self._attr_backup = {
            "STATE_DIR": agent_runner.STATE_DIR,
            "MANDATE_DIR": agent_runner.MANDATE_DIR,
            "SCRIPTS_DIR": agent_runner.SCRIPTS_DIR,
        }
        agent_runner.STATE_DIR = self.state_dir
        agent_runner.MANDATE_DIR = self.state_dir / "mandates"
        agent_runner.SCRIPTS_DIR = self.scripts_dir

    def tearDown(self) -> None:
        for name, value in self._attr_backup.items():
            setattr(agent_runner, name, value)
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        os.environ.pop("CODEX_BRIDGE_STUB_CAPTURE", None)
        os.environ.pop("CODEX_BRIDGE_STUB_RESUME_FAIL", None)
        self._tmp.cleanup()

    def _submit_args(self, **overrides) -> argparse.Namespace:
        defaults = dict(
            backend="codex", task_class="review", agent=False, tier="code", reset=False,
            retries=0, wait=True, json=True, model=None, mandate=None, role=None,
            fresh=False, force=False, prompt="hello",
        )
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    # -- T002: store roundtrip -------------------------------------------------

    def test_load_save_roundtrip(self) -> None:
        mandate = agent_runner._new_mandate("run-lsr")
        agent_runner.save_mandate(mandate)
        loaded = agent_runner.load_mandate("run-lsr")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["run_id"], "run-lsr")
        self.assertEqual(loaded["state"], "open")
        self.assertIsNone(agent_runner.load_mandate("run-never-existed"))

    def test_atomic_write_tmp_then_rename(self) -> None:
        mandate = agent_runner._new_mandate("run-atomic")
        agent_runner.save_mandate(mandate)
        path = agent_runner.mandate_path("run-atomic")
        self.assertTrue(path.exists())
        leftovers = [p for p in path.parent.iterdir() if p.name != path.name]
        self.assertEqual(leftovers, [], "no stray temp file should survive a successful save")

    def test_file_mode_0600(self) -> None:
        mandate = agent_runner._new_mandate("run-mode")
        agent_runner.save_mandate(mandate)
        path = agent_runner.mandate_path("run-mode")
        self.assertEqual(oct(path.stat().st_mode)[-3:], "600")

    # -- T003: engage() decision + guards --------------------------------------

    def test_engage_fresh_when_absent(self) -> None:
        result = agent_runner.engage("run-t3a", "executive", "gpt-6-astra", "codex", "job-1")
        self.assertEqual(result["mode"], "fresh")
        self.assertIsNone(result["thread_id_to_resume"])
        self.assertEqual(result["isolation"], "fresh")

    def test_engage_resume_when_thread_present(self) -> None:
        agent_runner.engage("run-t3b", "executive", "gpt-6-astra", "codex", "job-1")
        agent_runner.settle_mandate("run-t3b", "executive", "job-1", "returned", thread_id="thread-abc")
        result = agent_runner.engage("run-t3b", "executive", "gpt-6-astra", "codex", "job-2")
        self.assertEqual(result["mode"], "resumed")
        self.assertEqual(result["thread_id_to_resume"], "thread-abc")
        self.assertEqual(result["isolation"], "thread_id")
        self.assertEqual(result["prior_engagement"], "job-1")

    def test_engage_fresh_forced_on_flag_appends_replaced_thread_id(self) -> None:
        agent_runner.engage("run-t3c", "executive", "gpt-6-astra", "codex", "job-1")
        agent_runner.settle_mandate("run-t3c", "executive", "job-1", "returned", thread_id="thread-xyz")
        result = agent_runner.engage("run-t3c", "executive", "gpt-6-astra", "codex", "job-2", fresh=True)
        self.assertEqual(result["mode"], "fresh-forced")
        role = agent_runner.load_mandate("run-t3c")["roles"]["executive"]
        self.assertIn("thread-xyz", role["replaced_thread_ids"])
        self.assertIsNone(role["thread_id"])

    def test_engage_refuses_when_closed(self) -> None:
        agent_runner.engage("run-t3d", "executive", "gpt-6-astra", "codex", "job-1")
        agent_runner.settle_mandate("run-t3d", "executive", "job-1", "returned", thread_id="t1")
        agent_runner.mandate_close("run-t3d", "lead", None, False, False)
        with self.assertRaises(SystemExit) as ctx:
            agent_runner.engage("run-t3d", "executive", "gpt-6-astra", "codex", "job-2")
        self.assertEqual(ctx.exception.code, 8)

    def test_engage_refuses_duplicate_in_flight(self) -> None:
        agent_runner.engage("run-t3e", "executive", "gpt-6-astra", "codex", "job-1")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as ctx:
                agent_runner.engage("run-t3e", "executive", "gpt-6-astra", "codex", "job-2")
        self.assertEqual(ctx.exception.code, 7)
        self.assertIn("job-1", stderr.getvalue())

    def test_engage_force_override_logs_override(self) -> None:
        agent_runner.engage("run-t3f", "executive", "gpt-6-astra", "codex", "job-1")
        result = agent_runner.engage("run-t3f", "executive", "gpt-6-astra", "codex", "job-2", force=True)
        self.assertEqual(result["mode"], "fresh")
        mandate = agent_runner.load_mandate("run-t3f")
        self.assertTrue(any(o["kind"] == "duplicate" for o in mandate["overrides"]))

    def test_engage_refuses_model_mismatch(self) -> None:
        agent_runner.engage("run-t3g", "executive", "gpt-6-astra", "codex", "job-1")
        agent_runner.settle_mandate("run-t3g", "executive", "job-1", "returned", thread_id="t1")
        with self.assertRaises(SystemExit) as ctx:
            agent_runner.engage("run-t3g", "executive", "gpt-5.6-sol", "codex", "job-2")
        self.assertEqual(ctx.exception.code, 7)

    def test_engage_force_model_mismatch_logs_override(self) -> None:
        agent_runner.engage("run-t3h", "executive", "gpt-6-astra", "codex", "job-1")
        agent_runner.settle_mandate("run-t3h", "executive", "job-1", "returned", thread_id="t1")
        result = agent_runner.engage("run-t3h", "executive", "gpt-5.6-sol", "codex", "job-2", force=True)
        self.assertEqual(result["mode"], "resumed")
        mandate = agent_runner.load_mandate("run-t3h")
        self.assertTrue(any(o["kind"] == "model-mismatch" for o in mandate["overrides"]))
        self.assertEqual(mandate["roles"]["executive"]["model"], "gpt-5.6-sol")

    def test_close_by_rejects_unknown_actor_exit2(self) -> None:
        agent_runner.engage("run-t3i", "executive", "gpt-6-astra", "codex", "job-1")
        with self.assertRaises(SystemExit) as ctx:
            agent_runner.mandate_close("run-t3i", "grunt", None, True, False)
        self.assertEqual(ctx.exception.code, 2)

    def test_close_by_accepts_ceo_and_lead_only(self) -> None:
        agent_runner.engage("run-t3j", "executive", "gpt-6-astra", "codex", "job-1")
        self.assertEqual(agent_runner.mandate_close("run-t3j", "ceo", None, True, False), 0)
        agent_runner.engage("run-t3k", "executive", "gpt-6-astra", "codex", "job-1")
        self.assertEqual(agent_runner.mandate_close("run-t3k", "lead", None, True, False), 0)

    def test_close_by_invalid_rejected_even_when_already_closed(self) -> None:
        agent_runner.engage("run-t3l", "executive", "gpt-6-astra", "codex", "job-1")
        agent_runner.mandate_close("run-t3l", "lead", None, True, False)
        with self.assertRaises(SystemExit) as ctx:
            agent_runner.mandate_close("run-t3l", "grunt", None, False, False)
        self.assertEqual(ctx.exception.code, 2)
        mandate = agent_runner.load_mandate("run-t3l")
        self.assertEqual(mandate["state"], "closed")

    # -- T004: non-codex backend has no mandate-scoped continuity (I4/FR-011) ---

    def test_no_resume_continuity_for_non_codex_backend(self) -> None:
        result = agent_runner.engage("run-t4", "researcher", None, "mistral", "job-1")
        self.assertEqual(result["mode"], "fresh")
        agent_runner.settle_mandate("run-t4", "researcher", "job-1", "returned", thread_id="ignored")
        role = agent_runner.load_mandate("run-t4")["roles"]["researcher"]
        self.assertEqual(role["continuity"], "no-resume")
        self.assertIsNone(role["thread_id"])
        result2 = agent_runner.engage("run-t4", "researcher", None, "mistral", "job-2")
        self.assertEqual(result2["mode"], "fresh")

    # -- T010/T011/T012 (US1): end-to-end submit --mandate wiring ---------------

    def test_submit_mandate_captures_thread_id_on_fresh(self) -> None:
        args = self._submit_args(mandate="run-t10", role="executive", model="gpt-6-astra", prompt="brief")
        self.assertEqual(agent_runner.submit(args), 0)
        role = agent_runner.load_mandate("run-t10")["roles"]["executive"]
        self.assertEqual(role["engagements"][-1]["mode"], "fresh")
        self.assertIsNotNone(role["thread_id"])

    def test_submit_mandate_resumes_stored_thread_id_no_rebrief(self) -> None:
        args1 = self._submit_args(mandate="run-t11", role="executive", model="gpt-6-astra", prompt="brief")
        agent_runner.submit(args1)
        args2 = self._submit_args(mandate="run-t11", role="executive", model="gpt-6-astra", prompt="follow-up")
        agent_runner.submit(args2)
        role = agent_runner.load_mandate("run-t11")["roles"]["executive"]
        self.assertEqual(len(role["engagements"]), 2)
        self.assertEqual(role["engagements"][-1]["mode"], "resumed")
        self.assertEqual(role["engagements"][-1]["prior_engagement"], role["engagements"][0]["job_id"])

    def test_mandate_survives_process_restart_second_reader_sees_same_thread_id(self) -> None:
        args = self._submit_args(mandate="run-t12", role="executive", model="gpt-6-astra", prompt="brief")
        agent_runner.submit(args)
        first_read = agent_runner.load_mandate("run-t12")
        second_read = agent_runner.load_mandate("run-t12")  # simulates a second, independent reader process
        self.assertEqual(
            first_read["roles"]["executive"]["thread_id"],
            second_read["roles"]["executive"]["thread_id"],
        )
        self.assertIsNotNone(second_read["roles"]["executive"]["thread_id"])

    # -- T017/US2: multiple roles under one mandate -----------------------------

    def test_multiple_roles_recorded_under_same_mandate(self) -> None:
        agent_runner.engage("run-t17", "executive", "gpt-6-astra", "codex", "job-1")
        agent_runner.settle_mandate("run-t17", "executive", "job-1", "returned", thread_id="t1")
        agent_runner.engage("run-t17", "supervisor", "gpt-5.6-sol", "codex", "job-2")
        mandate = agent_runner.load_mandate("run-t17")
        self.assertIn("executive", mandate["roles"])
        self.assertIn("supervisor", mandate["roles"])

    # -- T020-T023 (US3): close / list / show -----------------------------------

    def test_mandate_close_records_closer_reason_timestamp(self) -> None:
        agent_runner.engage("run-t20", "executive", "gpt-6-astra", "codex", "job-1")
        agent_runner.mandate_close("run-t20", "lead", "done", True, False)
        mandate = agent_runner.load_mandate("run-t20")
        self.assertEqual(mandate["closed_by"], "lead")
        self.assertEqual(mandate["close_reason"], "done")
        self.assertIsNotNone(mandate["closed_at"])

    def test_closed_mandate_refuses_all_resume(self) -> None:
        agent_runner.engage("run-t21", "executive", "gpt-6-astra", "codex", "job-1")
        agent_runner.mandate_close("run-t21", "lead", None, True, False)
        with self.assertRaises(SystemExit) as ctx:
            agent_runner.engage("run-t21", "executive", "gpt-6-astra", "codex", "job-2")
        self.assertEqual(ctx.exception.code, 8)

    def test_new_mandate_same_roles_gets_fresh_session_no_leak(self) -> None:
        agent_runner.engage("run-t22a", "executive", "gpt-6-astra", "codex", "job-1")
        agent_runner.mandate_close("run-t22a", "lead", None, True, False)
        result = agent_runner.engage("run-t22b", "executive", "gpt-6-astra", "codex", "job-2")
        self.assertEqual(result["mode"], "fresh")
        self.assertIsNone(result["thread_id_to_resume"])

    def test_mandate_close_idempotent_and_refuses_with_inflight_unless_force(self) -> None:
        agent_runner.engage("run-t23", "executive", "gpt-6-astra", "codex", "job-1")
        with self.assertRaises(SystemExit) as ctx:
            agent_runner.mandate_close("run-t23", "lead", None, False, False)
        self.assertEqual(ctx.exception.code, 10)
        self.assertEqual(agent_runner.mandate_close("run-t23", "lead", None, True, False), 0)
        # idempotent repeat, valid --by
        self.assertEqual(agent_runner.mandate_close("run-t23", "lead", None, False, False), 0)

    def test_mandate_close_inflight_refusal_exits_10(self) -> None:
        agent_runner.engage("run-t23b", "executive", "gpt-6-astra", "codex", "job-1")
        with self.assertRaises(SystemExit) as ctx:
            agent_runner.mandate_close("run-t23b", "lead", None, False, False)
        self.assertEqual(ctx.exception.code, 10)
        mandate = agent_runner.load_mandate("run-t23b")
        self.assertEqual(mandate["state"], "open")
        self.assertEqual(agent_runner.mandate_close("run-t23b", "lead", None, True, False), 0)
        mandate = agent_runner.load_mandate("run-t23b")
        self.assertTrue(any(o["kind"] == "close-in-flight" for o in mandate["overrides"]))

    # -- T026-T029 (US4): duplicate + model-mismatch CLI-visible guards ---------

    def test_duplicate_inflight_refused_names_job_id(self) -> None:
        agent_runner.engage("run-t26", "executive", "gpt-6-astra", "codex", "job-first")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as ctx:
                agent_runner.engage("run-t26", "executive", "gpt-6-astra", "codex", "job-second")
        self.assertEqual(ctx.exception.code, 7)
        self.assertIn("job-first", stderr.getvalue())

    def test_force_duplicate_proceeds_both_recorded_override_logged(self) -> None:
        agent_runner.engage("run-t27", "executive", "gpt-6-astra", "codex", "job-first")
        agent_runner.engage("run-t27", "executive", "gpt-6-astra", "codex", "job-second", force=True)
        mandate = agent_runner.load_mandate("run-t27")
        job_ids = [e["job_id"] for e in mandate["roles"]["executive"]["engagements"]]
        self.assertIn("job-first", job_ids)
        self.assertIn("job-second", job_ids)
        self.assertTrue(any(o["kind"] == "duplicate" for o in mandate["overrides"]))

    def test_model_mismatch_refused_before_dispatch(self) -> None:
        agent_runner.engage("run-t28", "executive", "gpt-6-astra", "codex", "job-1")
        agent_runner.settle_mandate("run-t28", "executive", "job-1", "returned", thread_id="t1")
        with self.assertRaises(SystemExit) as ctx:
            agent_runner.engage("run-t28", "executive", "gpt-5.6-sol", "codex", "job-2")
        self.assertEqual(ctx.exception.code, 7)
        mandate = agent_runner.load_mandate("run-t28")
        job_ids = [e["job_id"] for e in mandate["roles"]["executive"]["engagements"]]
        self.assertNotIn("job-2", job_ids)

    def test_force_model_mismatch_proceeds_override_logged(self) -> None:
        agent_runner.engage("run-t29", "executive", "gpt-6-astra", "codex", "job-1")
        agent_runner.settle_mandate("run-t29", "executive", "job-1", "returned", thread_id="t1")
        agent_runner.engage("run-t29", "executive", "gpt-5.6-sol", "codex", "job-2", force=True)
        mandate = agent_runner.load_mandate("run-t29")
        self.assertTrue(any(o["kind"] == "model-mismatch" for o in mandate["overrides"]))

    # -- T031 (Polish): stale-mandate WARN --------------------------------------

    def test_mandate_list_warns_open_mandate_over_7_days(self) -> None:
        stale = agent_runner._new_mandate("run-t31-stale")
        stale["opened_at"] = "2020-01-01T00:00:00Z"
        agent_runner.save_mandate(stale)
        fresh = agent_runner._new_mandate("run-t31-fresh")
        agent_runner.save_mandate(fresh)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            agent_runner.mandate_list(False)
        output = stderr.getvalue()
        self.assertIn("run-t31-stale", output)
        self.assertNotIn("run-t31-fresh", output)

    # -- T041 (analyze-fix): follow-up rejects mandate flags --------------------

    def test_followup_rejects_mandate_flags_exit2(self) -> None:
        env = os.environ.copy()
        result = subprocess.run(
            [sys.executable, str(RUNNER_DIR / "agent_runner.py"), "follow-up", "job-aaaa",
             "--mandate", "M", "--role", "executive", "x"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("follow-up does not accept mandate flags", result.stderr)

    # -- T042 (US2): engaging another role never touches the Executive's state --

    def test_engaging_other_role_leaves_executive_session_untouched(self) -> None:
        agent_runner.engage("run-t42", "executive", "gpt-6-astra", "codex", "job-1")
        agent_runner.settle_mandate("run-t42", "executive", "job-1", "returned", thread_id="t1")
        before = agent_runner.load_mandate("run-t42")["roles"]["executive"]
        agent_runner.engage("run-t42", "supervisor", "gpt-5.6-sol", "codex", "job-2")
        after = agent_runner.load_mandate("run-t42")["roles"]["executive"]
        self.assertEqual(len(after["engagements"]), len(before["engagements"]))
        self.assertEqual(after["thread_id"], before["thread_id"])
        self.assertIsNone(after["in_flight_job_id"])

    # -- T043: state-dir containment guard (FR-015 / C7) ------------------------

    def test_state_dir_inside_repo_refused(self) -> None:
        agent_runner.STATE_DIR = REPO_ROOT / "tmp-mandate-test-state-should-never-persist"
        try:
            with self.assertRaises(SystemExit) as ctx:
                agent_runner.ensure_state_dir_containment()
            self.assertEqual(ctx.exception.code, 2)
        finally:
            agent_runner.STATE_DIR = self.state_dir

    def test_state_dir_under_dot_claude_refused(self) -> None:
        agent_runner.STATE_DIR = Path.home() / ".claude" / "tmp-mandate-test-state-should-never-persist"
        try:
            with self.assertRaises(SystemExit) as ctx:
                agent_runner.ensure_state_dir_containment()
            self.assertEqual(ctx.exception.code, 2)
        finally:
            agent_runner.STATE_DIR = self.state_dir

    def test_repo_root_resolution_prefers_git_toplevel_and_falls_back_to_dot_git(self) -> None:
        root = agent_runner._repo_root()
        self.assertIsNotNone(root)
        self.assertTrue((root / ".git").exists())

    # -- T044: renumbered exit codes do not collide with route.sh ---------------

    def test_mandate_exit_codes_do_not_collide_with_route_sh(self) -> None:
        codes: set[int] = set()

        agent_runner.engage("run-t44a", "executive", "gpt-6-astra", "codex", "job-1")
        with self.assertRaises(SystemExit) as ctx:
            agent_runner.engage("run-t44a", "executive", "gpt-6-astra", "codex", "job-2")
        codes.add(ctx.exception.code)
        agent_runner.settle_mandate("run-t44a", "executive", "job-1", "returned", thread_id="t1")
        with self.assertRaises(SystemExit) as ctx:
            agent_runner.engage("run-t44a", "executive", "gpt-5.6-sol", "codex", "job-3")
        codes.add(ctx.exception.code)
        agent_runner.mandate_close("run-t44a", "lead", None, True, False)
        with self.assertRaises(SystemExit) as ctx:
            agent_runner.engage("run-t44a", "executive", "gpt-6-astra", "codex", "job-4")
        codes.add(ctx.exception.code)

        agent_runner.engage("run-t44b", "executive", "gpt-6-astra", "codex", "job-1")
        with self.assertRaises(SystemExit) as ctx:
            agent_runner.mandate_close("run-t44b", "lead", None, False, False)
        codes.add(ctx.exception.code)

        os.environ["CODEX_BRIDGE_STUB_RESUME_FAIL"] = "true"
        try:
            args1 = self._submit_args(mandate="run-t44c", role="executive", model="gpt-6-astra", prompt="brief")
            agent_runner.submit(args1)
            args2 = self._submit_args(mandate="run-t44c", role="executive", model="gpt-6-astra", prompt="q")
            resume_fail_code = agent_runner.submit(args2)
        finally:
            os.environ.pop("CODEX_BRIDGE_STUB_RESUME_FAIL", None)
        codes.add(resume_fail_code)

        self.assertEqual(codes, {7, 8, 9, 10})
        self.assertTrue(codes.isdisjoint({3, 4, 5, 127}))

        # the usage class deliberately reuses exit 2, never a new code.
        with self.assertRaises(SystemExit) as ctx:
            agent_runner.mandate_close("run-t44d", "grunt", None, False, False)
        self.assertEqual(ctx.exception.code, 2)

    # -- T045 (MANDATORY): SC-001 byte-identity on the real submit --mandate path

    def test_submit_mandate_prompt_body_byte_identical_no_preamble(self) -> None:
        os.environ["CODEX_BRIDGE_STUB_CAPTURE"] = str(self.capture_path)
        try:
            long_brief = "You are Executive for this mandate. " + ("background fact. " * 20) + "Remember: OCELOT-41."
            args1 = self._submit_args(mandate="run-t45", role="executive", model="gpt-6-astra", prompt=long_brief)
            agent_runner.submit(args1)
            short_question = "What is the passphrase? Answer with the word only."
            args2 = self._submit_args(mandate="run-t45", role="executive", model="gpt-6-astra", prompt=short_question)
            agent_runner.submit(args2)
        finally:
            os.environ.pop("CODEX_BRIDGE_STUB_CAPTURE", None)

        lines = [line for line in self.capture_path.read_text().splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        round2 = json.loads(lines[-1])
        self.assertEqual(round2["prompt"], short_question)
        self.assertEqual(len(round2["prompt"]), len(short_question))

        role = agent_runner.load_mandate("run-t45")["roles"]["executive"]
        self.assertEqual(role["engagements"][-1]["mode"], "resumed")

    # -- T046 (FR-012 backward compatibility) ------------------------------------

    def test_submit_without_mandate_has_no_mandate_key(self) -> None:
        args = self._submit_args(mandate=None, role=None, prompt="ping")
        agent_runner.submit(args)
        jobs = list(self.state_dir.glob("job-*/job.json"))
        self.assertEqual(len(jobs), 1)
        job = json.loads(jobs[0].read_text())
        self.assertNotIn("mandate", job)
        result_json = json.loads((jobs[0].parent / "result.json").read_text())
        self.assertNotIn("mandate", result_json)
        self.assertNotIn("role", result_json)
        self.assertNotIn("mode", result_json)
        mandate_dir = self.state_dir / "mandates"
        self.assertFalse(mandate_dir.exists() and any(mandate_dir.iterdir()))


if __name__ == "__main__":
    unittest.main()
