"""022 US3: sandbox probe, per-turn deadline, counter lock, wait docstring. Temp dirs, no network, no real sandbox."""
from __future__ import annotations
import io
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from agents_inc.install import dispatch, mcp_broker
from tests.test_dispatch_failloud import launch_result
from tests.test_dispatch_snapshot_trust import DispatchBase

_ALLOW = mock.patch.dict(os.environ, {dispatch.ALLOW_SANDBOXED_ENV: "1"})


def setUpModule():
    _ALLOW.start()  # #94: real launch() calls stay allowed when the suite runs inside a sandbox


def tearDownModule():
    _ALLOW.stop()


class SandboxProbeTest(unittest.TestCase):
    def setUp(self):
        reset = mock.patch.object(dispatch, "_SANDBOX_OK", None, create=True)
        reset.start()
        self.addCleanup(reset.stop)
        exe = mock.patch.object(dispatch.os, "access", return_value=True)
        exe.start()
        self.addCleanup(exe.stop)
        plat = mock.patch.object(dispatch.sys, "platform", "darwin")
        plat.start()
        self.addCleanup(plat.stop)

    def test_failing_probe_is_unavailable(self):
        bad = mock.Mock(returncode=71)
        with mock.patch.object(dispatch.subprocess, "run", return_value=bad):
            self.assertFalse(dispatch.sandbox_available())

    def test_probe_oserror_and_timeout_are_unavailable(self):
        for exc in (OSError("nope"), dispatch.subprocess.TimeoutExpired("x", 10)):
            with self.subTest(exc=type(exc).__name__):
                dispatch._SANDBOX_OK = None
                with mock.patch.object(dispatch.subprocess, "run", side_effect=exc):
                    self.assertFalse(dispatch.sandbox_available())

    def test_good_probe_is_cached(self):
        good = mock.Mock(returncode=0)
        with mock.patch.object(dispatch.subprocess, "run", return_value=good) as run:
            self.assertTrue(dispatch.sandbox_available())
            self.assertTrue(dispatch.sandbox_available())
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][0], dispatch.SANDBOX_EXEC)

    def test_non_darwin_never_probes(self):
        with mock.patch.object(dispatch.sys, "platform", "linux"), \
                mock.patch.object(dispatch.subprocess, "run") as run:
            self.assertFalse(dispatch.sandbox_available())
        run.assert_not_called()

    def test_validate_fields_refuses_claude_when_probe_fails(self):
        with mock.patch.object(dispatch, "sandbox_available", return_value=False):
            self.assertTrue(dispatch._kind("haiku") == "claude")
            src = Path(dispatch.__file__).read_text()
        self.assertIn('return None, "no-sandbox-backend"', src)


class TurnTimeoutTest(DispatchBase):
    def _argv(self, pid_file: Path):
        code = f"import os,time;open({str(pid_file)!r},'w').write(str(os.getpid()));time.sleep(30)"
        return lambda *a, **k: [sys.executable, "-c", code]

    def test_launch_kills_group_and_returns_124(self):
        pid_file = self.root / "child.pid"
        run_dir = self.root / "rd"
        run_dir.mkdir()
        env = {"AGENTS_INC_TURN_TIMEOUT_S": "1"}
        with mock.patch.dict(os.environ, env), mock.patch.object(dispatch, "claude_argv", self._argv(pid_file)):
            start = time.monotonic()
            res = dispatch.launch("claude", "sonnet", None, self.repo, "prompt", run_dir)
        self.assertLess(time.monotonic() - start, 6)
        self.assertEqual(res["rc"], 124)
        self.assertIn("turn timeout after", res["stderr"])
        pid = int(pid_file.read_text())
        deadline = time.monotonic() + 3
        gone = False
        while time.monotonic() < deadline and not gone:
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                gone = True
        self.assertTrue(gone, "child survived the deadline")

    def test_zero_means_no_deadline(self):
        run_dir = self.root / "rd"
        run_dir.mkdir()
        fast = lambda *a, **k: [sys.executable, "-c", "print('{}')"]
        with mock.patch.dict(os.environ, {"AGENTS_INC_TURN_TIMEOUT_S": "0"}), \
                mock.patch.object(dispatch, "claude_argv", fast):
            res = dispatch.launch("claude", "sonnet", None, self.repo, "prompt", run_dir)
        self.assertEqual(res["rc"], 0)

    def test_timeout_marker_maps_to_timeout_reason(self):
        rc, out, _ = self.dispatch(launch_result("", rc=124, stderr="turn timeout after 1 s"))
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.spec()["reason"], "timeout")

    def test_plain_124_is_not_timeout(self):
        rc, out, _ = self.dispatch(launch_result("", rc=124, stderr="other"))
        self.assertEqual(self.spec()["reason"], "rc-nonzero")


class BrokerResumeLaunchFailTest(DispatchBase):
    def test_failed_resume_reaches_lead_and_counts_as_turn(self):
        from tests.test_dispatch_snapshot_trust import ok_launch
        self.dispatch(ok_launch())
        child = self.run_dir()
        parent = {"cwd": str(self.repo), "request_counts": {"red": 0}, "resumes": 0}
        plan = {"child": child, "new_rid": "req-r1", "root": "req", "turn": 1}
        with mock.patch.object(dispatch, "launch", side_effect=FileNotFoundError("claude missing")), \
                mock.patch.object(dispatch, "_in_worker_scope", side_effect=lambda run, rid, out, fn, spec: (fn(), None)):
            result, _ = dispatch.run_resume(self.runs, plan, "continue", parent, None)
        self.assertEqual((result["outcome"], result["reason"]), ("red", "launch-failed"))
        self.assertEqual(result["status"], "red")
        cspec = json.loads((child / "run.json").read_text())
        self.assertEqual(len(cspec["resumes"]), 1, "failed attempt must count as a turn")
        self.assertEqual(parent["resumes"], 1)


class LockProbe:
    """Stand-in for _SPEC_LOCK that counts how deep the holders are."""

    def __init__(self):
        self.depth = 0

    def __enter__(self):
        self.depth += 1
        return self

    def __exit__(self, *exc):
        self.depth -= 1
        return False


class GuardedCounts(dict):
    def __init__(self, probe, *a):
        super().__init__(*a)
        self.probe = probe
        self.unlocked = []

    def __setitem__(self, key, value):
        if not self.probe.depth:
            self.unlocked.append(key)
        super().__setitem__(key, value)


class CounterLockTest(DispatchBase):
    def _counts(self, probe):
        return GuardedCounts(probe, {"duplicate": 0, "refused": 0})

    def test_dispatch_duplicate_and_refused_hold_lock(self):
        probe = LockProbe()
        run_dir = self.root / "rd"
        (run_dir / dispatch.INBOX).mkdir(parents=True)
        (run_dir / dispatch.INBOX / "a1.request.json").write_text("{}")
        (run_dir / dispatch.INBOX / "b2.request.json").write_text("not json")
        spec = {"request_counts": self._counts(probe), "fan_out": {"width": 0, "total": 0, "depth": 0}}
        with mock.patch.object(dispatch, "_SPEC_LOCK", probe):
            dispatch._handle_one(run_dir, "a1.request.json", spec, {"a1"}, None)
            dispatch._handle_one(run_dir, "b2.request.json", spec, set(), None)
        self.assertEqual(spec["request_counts"]["duplicate"], 1)
        self.assertEqual(spec["request_counts"]["refused"], 1)
        self.assertEqual(spec["request_counts"].unlocked, [])

    def test_mcp_broker_refusals_hold_lock(self):
        probe = LockProbe()
        run_dir = self.root / "lead"
        run_dir.mkdir()
        broker = mcp_broker.Broker(run_dir)
        broker.spec = {"request_counts": self._counts(probe), "worker_models": ["haiku"],
                       "fan_out": {"width": 1, "total": 1, "depth": 1}, "workers_spawned": 0}
        with mock.patch.object(dispatch, "_SPEC_LOCK", probe), \
                mock.patch.object(broker, "ensure"), mock.patch.object(broker, "issue"), \
                mock.patch.object(broker, "save"), \
                mock.patch.object(dispatch, "_validate_fields", return_value=(None, "bad-keys")), \
                mock.patch.object(dispatch, "_write_request_result"):
            broker.tool_dispatch({"model": "haiku", "effort": "low", "slots": {}})
            stdin = [("x" * (dispatch.REQUEST_MAX_BYTES + 10) + "\n")]
            out = io.StringIO()
            with mock.patch.object(mcp_broker, "Broker", return_value=broker), \
                    mock.patch.object(mcp_broker, "_frames", return_value=iter([("x", True)])):
                mcp_broker.serve(run_dir, stdin, out)
        self.assertEqual(broker.spec["request_counts"]["refused"], 2)
        self.assertEqual(broker.spec["request_counts"].unlocked, [])


class WaitDocTest(unittest.TestCase):
    def test_docstring_states_real_exit_codes(self):
        doc = dispatch.wait.__doc__
        self.assertIn("124 on timeout", doc)
        self.assertIn("non-positive timeout", doc)


if __name__ == "__main__":
    unittest.main()
