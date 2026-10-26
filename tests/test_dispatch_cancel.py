"""Spec 027 US3: cancelling a dispatch run. SIGTERM, SIGHUP and SIGINT end the run `cancelled` and kill the delegate's
process group; `dispatch --cancel RUN_DIR` kills a recorded group only while the run has no final outcome and the
group leader is still the process dispatch started. Writes only to temp dirs; fake CLIs come from fixtures/live-events."""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from agents_inc.install import cli, dispatch
from tests.test_dispatch_cli import CliBase
from tests.test_live_events_golden import FakeCliMixin, setUpModule as golden_setup, tearDownModule as golden_teardown

SIGNALS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)


class _Stray(Exception):
    """Raised by the test's own handler when dispatch installed none: the red phase fails instead of killing the runner."""


def _stray(signum, frame):
    raise _Stray(signal.Signals(signum).name)


def _gone(pgid: int, within: float) -> bool:
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


class SignalCancelTest(FakeCliMixin, CliBase):
    def setUp(self):
        super().setUp()
        self.saved = {s: signal.getsignal(s) for s in SIGNALS}
        for s in SIGNALS:
            signal.signal(s, _stray)
        self.addCleanup(lambda: [signal.signal(s, h) for s, h in self.saved.items()])

    def _signal_when_running(self, signum: int) -> threading.Thread:
        """After the delegate's first event lands in events.jsonl, send signum to this process."""
        def send():
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                for path in self.runs.glob("*/events.jsonl") if self.runs.exists() else ():
                    if '"source": "claude"' in path.read_text(encoding="utf-8") or \
                            '"source": "codex"' in path.read_text(encoding="utf-8"):
                        time.sleep(0.3)  # on_start has recorded the group by now
                        os.kill(os.getpid(), signum)
                        return
                time.sleep(0.05)
        thread = threading.Thread(target=send, daemon=True)
        thread.start()
        return thread

    def _cancel_with(self, model: str, signum: int):
        sender = self._signal_when_running(signum)
        rc, out, _, run = self._dispatch(model, env={"FAKE_SLEEP": "1"})
        sender.join(5)
        spec = json.loads((run / "run.json").read_text(encoding="utf-8"))
        events = [json.loads(ln) for ln in (run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        return rc, out, run, spec, events

    def test_each_signal_ends_the_run_cancelled(self):
        for model in ("haiku", "sol"):
            for signum in SIGNALS:
                with self.subTest(model=model, signal=signal.Signals(signum).name):
                    for old in self.runs.glob("*") if self.runs.exists() else ():
                        subprocess.run(["rm", "-rf", str(old)], check=True)
                    rc, out, run, spec, events = self._cancel_with(model, signum)
                    self.assertEqual(rc, 130)
                    self.assertEqual(out.strip(), f"dispatch {run.name} {model} cancelled")
                    self.assertEqual(spec["outcome"], "cancelled")
                    self.assertEqual(events[-1]["event"]["type"], "run.end")
                    self.assertEqual(events[-1]["event"]["outcome"], "cancelled")
                    self.assertTrue(_gone(spec["delegate_pgid"], 5), "delegate group still alive after 5 s")

    def test_handlers_are_put_back_after_the_run(self):
        self._cancel_with("haiku", signal.SIGTERM)
        self.assertIs(signal.getsignal(signal.SIGTERM), _stray)


def _start_of(pid: int) -> str:
    try:
        return subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    except OSError:
        raise unittest.SkipTest("ps unavailable here")


class CancelFlagTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        if not dispatch._process_start(os.getpid()):
            self.skipTest("ps unavailable here")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name)
        self.procs: list = []
        self.addCleanup(self._reap)

    def _reap(self):
        for p in self.procs:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            p.wait()

    def _sleeper(self) -> subprocess.Popen:
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
        self.procs.append(p)
        return p

    def _record(self, **fields):
        (self.run_dir / "run.json").write_text(json.dumps(fields), encoding="utf-8")

    def _cancel(self) -> tuple[int, str]:
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli.main(["dispatch", "--cancel", str(self.run_dir)])
        return rc, out.getvalue().strip()

    def test_live_group_is_killed(self):
        p = self._sleeper()
        self._record(outcome=None, delegate_pgid=p.pid, delegate_start=_start_of(p.pid))
        rc, out = self._cancel()
        self.assertEqual(rc, 0)
        self.assertNotIn("nothing to cancel", out)
        p.wait(timeout=8)
        self.assertIsNotNone(p.returncode)

    def test_final_outcome_means_nothing_to_cancel(self):
        p = self._sleeper()
        self._record(outcome="green", delegate_pgid=p.pid, delegate_start=_start_of(p.pid))
        rc, out = self._cancel()
        self.assertEqual((rc, out), (0, "nothing to cancel"))
        self.assertIsNone(p.poll())

    def test_leader_that_is_not_the_recorded_process_is_left_alone(self):
        p = self._sleeper()
        self._record(outcome=None, delegate_pgid=p.pid, delegate_start="Thu Jan  1 00:00:00 1970")
        rc, out = self._cancel()
        self.assertEqual((rc, out), (0, "nothing to cancel"))
        self.assertIsNone(p.poll())

    def test_missing_run_json_or_group_is_nothing_to_cancel(self):
        self.assertEqual(self._cancel(), (0, "nothing to cancel"))
        self._record(outcome=None)
        self.assertEqual(self._cancel(), (0, "nothing to cancel"))


def setUpModule():
    golden_setup()


def tearDownModule():
    golden_teardown()


if __name__ == "__main__":
    unittest.main()
