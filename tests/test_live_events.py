"""Spec 027: live events. EventSink, the streaming runner, the Claude result parse and the dispatch lifecycle.
Writes only to temp dirs; fake CLIs come from fixtures/live-events."""
from __future__ import annotations
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import shutil
import threading

from agents_inc.install import dispatch, live_events
from agents_inc.install.live_events import EventSink
from tests.test_dispatch_cli import CliBase
from tests.test_live_events_golden import FakeCliMixin, setUpModule as golden_setup, tearDownModule as golden_teardown

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "fixtures/live-events"
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def read_events(run_dir: Path) -> list[dict]:
    path = Path(run_dir) / "events.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


class EventSinkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_envelope_fields_and_seq_from_one(self):
        sink = EventSink(self.dir)
        sink.emit("agents-inc", {"type": "run.start", "run_id": "r1"})
        sink.emit("codex", {"type": "turn.started"})
        sink.close()
        first, second = read_events(self.dir)
        self.assertEqual(set(first), {"v", "seq", "ts", "source", "event"})
        self.assertEqual((first["v"], first["seq"], first["source"]), (1, 1, "agents-inc"))
        self.assertEqual(first["event"], {"type": "run.start", "run_id": "r1"})
        self.assertRegex(first["ts"], TS_RE)
        self.assertEqual((second["seq"], second["source"], second["event"]), (2, "codex", {"type": "turn.started"}))

    def test_line_parses_json_and_wraps_noise(self):
        sink = EventSink(self.dir)
        sink.line("codex", '{"type": "turn.started"}')
        sink.line("codex", "not json at all")
        sink.line("claude", "[1, 2]")  # JSON but not an object: noise
        sink.close()
        events = [e["event"] for e in read_events(self.dir)]
        self.assertEqual(events, [{"type": "turn.started"}, {"type": "raw", "text": "not json at all"},
                                  {"type": "raw", "text": "[1, 2]"}])

    def test_each_line_is_flushed_before_the_next(self):
        sink = EventSink(self.dir)
        sink.emit("codex", {"type": "a"})
        self.assertEqual(len(read_events(self.dir)), 1)  # readable with the sink still open
        sink.emit("codex", {"type": "b"})
        self.assertEqual(len(read_events(self.dir)), 2)
        sink.close()

    def test_file_mode_is_0600(self):
        for safe in (False, True):
            run = self.dir / f"safe{safe}"
            run.mkdir()
            sink = EventSink(run, safe_writes=safe)
            sink.emit("agents-inc", {"type": "run.start"})
            sink.close()
            self.assertEqual(stat.S_IMODE((run / "events.jsonl").stat().st_mode), 0o600)

    def test_safe_writes_refuses_a_planted_link(self):
        target = self.dir / "victim.txt"
        target.write_text("keep")
        (self.dir / "events.jsonl").symlink_to(target)
        sink = EventSink(self.dir, safe_writes=True)
        sink.emit("agents-inc", {"type": "run.start"})
        sink.close()
        self.assertEqual(target.read_text(), "keep")
        self.assertTrue(sink.error)

    def test_safe_writes_refuses_an_existing_file(self):
        (self.dir / "events.jsonl").write_text("old\n")
        sink = EventSink(self.dir, safe_writes=True)
        sink.emit("agents-inc", {"type": "run.start"})
        self.assertEqual((self.dir / "events.jsonl").read_text(), "old\n")
        self.assertTrue(sink.error)

    def test_long_line_is_cut_and_marked(self):
        sink = EventSink(self.dir, line_cap=64)
        sink.line("codex", "x" * 500)
        sink.emit("codex", {"type": "big", "blob": "y" * 500})
        sink.line("codex", '{"type": "small"}')
        sink.close()
        big_raw, big_obj, small = read_events(self.dir)
        self.assertEqual(big_raw["event"]["text"], "x" * 64)
        for env in (big_raw, big_obj):
            self.assertIs(env["cut"], True)
            self.assertEqual(env["event"]["type"], "raw")
            self.assertEqual(len(env["event"]["text"].encode()), 64)
        self.assertNotIn("cut", small)

    def test_default_line_cap_is_64_kib(self):
        self.assertEqual(live_events.LINE_CAP, 64 * 1024)
        self.assertEqual(live_events.TOTAL_CAP, 64 * 1024 * 1024)

    def test_total_cap_writes_one_truncated_event_then_stops_provider_events(self):
        sink = EventSink(self.dir, total_cap=400)
        for i in range(20):
            sink.emit("codex", {"type": "n", "i": i})
        sink.emit("agents-inc", {"type": "run.end", "outcome": "done", "rc": 0})  # lifecycle still lands
        sink.close()
        events = read_events(self.dir)
        types = [e["event"]["type"] for e in events]
        self.assertEqual(types.count("events.truncated"), 1)
        self.assertEqual(types[-1], "run.end")
        self.assertEqual(types[-2], "events.truncated")
        self.assertLess(types.count("n"), 20)
        self.assertEqual([e["seq"] for e in events], list(range(1, len(events) + 1)))

    def test_oserror_disables_the_sink_and_reports(self):
        sink = EventSink(self.dir)
        sink.emit("codex", {"type": "a"})
        with mock.patch("os.write", side_effect=OSError("disk full")):
            sink.emit("codex", {"type": "b"})  # never raises into dispatch
        sink.emit("codex", {"type": "c"})
        sink.close()
        self.assertIn("disk full", sink.error)
        self.assertEqual([e["event"]["type"] for e in read_events(self.dir)], ["a"])

    def test_open_failure_disables_the_sink(self):
        sink = EventSink(self.dir / "missing")
        sink.emit("codex", {"type": "a"})
        sink.close()
        self.assertTrue(sink.error)

    def test_no_error_when_all_goes_well(self):
        sink = EventSink(self.dir)
        sink.emit("codex", {"type": "a"})
        sink.close()
        self.assertIsNone(sink.error)


def _spawn(code: str, **kw) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-u", "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True, **kw)


def _group_gone(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    return False


class StreamRunTest(unittest.TestCase):
    def test_lines_reach_on_line_before_the_child_exits(self):
        proc = _spawn("import sys,time\nprint('a')\ntime.sleep(1.0)\nprint('b')\n")
        seen = []
        rc, out, err = live_events._stream_run(proc, "", 30, lambda ln: seen.append((ln, proc.poll())))
        self.assertEqual((rc, out, err), (0, "a\nb\n", ""))
        self.assertEqual([ln for ln, _ in seen], ["a", "b"])
        self.assertIsNone(seen[0][1], "first line must arrive while the child still runs")

    def test_prompt_reaches_stdin_and_stderr_is_kept_apart(self):
        proc = _spawn("import sys\nsys.stderr.write('E'*200000)\nprint(sys.stdin.read().upper())\n")
        rc, out, err = live_events._stream_run(proc, "hello", 30, None)
        self.assertEqual((rc, out), (0, "HELLO\n"))
        self.assertEqual(len(err), 200000)

    def test_exit_code_is_returned(self):
        rc, out, _ = live_events._stream_run(_spawn("print('x')\nraise SystemExit(3)\n"), "", 30, None)
        self.assertEqual((rc, out), (3, "x\n"))

    def test_deadline_kills_the_group_and_marks_timeout(self):
        # the shell child leaves a sleeping grandchild in the same group; both must die
        proc = _spawn("import os,time\nos.system('sleep 60 &')\nprint('up', flush=True)\ntime.sleep(60)\n")
        started = time.monotonic()
        rc, out, err = live_events._stream_run(proc, "", 0.7, None)
        self.assertLess(time.monotonic() - started, 15)
        self.assertEqual(rc, 124)
        self.assertTrue(err.endswith("turn timeout after 0.7 s"), err)
        time.sleep(0.2)
        self.assertTrue(_group_gone(proc.pid))
        self.assertIsNotNone(proc.returncode)

    def test_base_exception_kills_and_reaps(self):
        proc = _spawn("import time\nprint('up', flush=True)\ntime.sleep(60)\n")

        def boom(*_):
            raise KeyboardInterrupt

        old = signal.signal(signal.SIGALRM, boom)
        signal.setitimer(signal.ITIMER_REAL, 0.4)
        try:
            with self.assertRaises(KeyboardInterrupt):
                live_events._stream_run(proc, "", 30, None)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
        self.assertIsNotNone(proc.returncode)
        self.assertTrue(_group_gone(proc.pid))

    def test_start_callback_gets_the_pid(self):
        pids = []
        proc = _spawn("print('x')\n")
        live_events._stream_run(proc, "", 30, None, on_start=pids.append)
        self.assertEqual(pids, [proc.pid])

    def test_proc_without_pipes_uses_communicate(self):
        proc = SimpleNamespace(pid=0, returncode=None, stdout=None)

        def communicate(input=None, timeout=None):
            proc.returncode = 0
            return "l1\nl2\n", "warn"
        proc.communicate = communicate
        seen = []
        self.assertEqual(live_events._stream_run(proc, "p", 5, seen.append), (0, "l1\nl2\n", "warn"))
        self.assertEqual(seen, ["l1", "l2"])


class ClaudeResultParseTest(unittest.TestCase):
    """FR-003 / research R1: the final `type: "result"` message yields today's stdout, session_id, is_error, usage.

    [assumed] until T043 confirms against a real stream: `claude -p --output-format stream-json` needs `--verbose`,
    and its `result` message carries `result`, `session_id`, `is_error`, `modelUsage`, `total_cost_usd`,
    `num_turns` and `duration_ms` like the `json` payload."""

    GOOD = ("caveman ultra confirmed. GRILL: none. [verified] gate rc=0 exit code 0.\n"
            "OUT OF SCOPE / INCOMPLETE: none\nWORKERS SPAWNED: 0\n")

    def parse(self, stdout: str):
        from agents_inc.install import dispatch
        return dispatch.parse_claude_output(stdout)

    def test_stream_fixture_yields_the_result_message(self):
        from agents_inc.install import dispatch
        stdout = (FIXTURES / "claude.jsonl").read_text(encoding="utf-8")
        final = json.loads(stdout.splitlines()[-1])
        text, session, is_error, usage = self.parse(stdout)
        self.assertEqual((text, session, is_error), (self.GOOD, "sess-fixture-1", False))
        self.assertEqual(usage, dispatch.claude_usage(final))
        self.assertEqual(usage["input_tokens"], 1500)

    def test_last_result_message_wins_and_noise_is_skipped(self):
        first = json.dumps({"type": "result", "result": "old", "session_id": "s1"})
        last = json.dumps({"type": "result", "result": "new", "session_id": "s2", "is_error": True})
        text, session, is_error, usage = self.parse(f"{first}\nnoise line\n{last}\n[1]\n")
        self.assertEqual((text, session, is_error, usage), ("new", "s2", True, None))

    def test_legacy_single_payload(self):
        payload = json.dumps({"result": "ok", "session_id": "s", "is_error": False})
        self.assertEqual(self.parse(payload), ("ok", "s", False, None))

    def test_raw_fallback(self):
        self.assertEqual(self.parse("plain text, no json"), ("plain text, no json", None, False, None))
        self.assertEqual(self.parse(""), ("", None, False, None))

    def test_stream_without_a_result_message_is_raw(self):
        stdout = '{"type": "assistant", "message": {}}\n'
        self.assertEqual(self.parse(stdout), (stdout, None, False, None))

    def test_non_string_result_is_stringified_like_today(self):
        self.assertEqual(self.parse(json.dumps({"type": "result", "result": 5}))[0], "5")


def read_events(run_dir: Path) -> list:
    return [json.loads(ln) for ln in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]


class LifecycleTest(FakeCliMixin, CliBase):
    """FR-001, FR-002, FR-007, FR-008, FR-010: events.jsonl through a real dispatch run against the fake CLIs."""

    def _kinds(self, run_dir: Path) -> list:
        return [(e["source"], e["event"].get("type")) for e in read_events(run_dir)]

    def _ends(self, run_dir: Path) -> dict:
        end = read_events(run_dir)[-1]
        self.assertEqual((end["source"], end["event"]["type"]), ("agents-inc", "run.end"))
        return end["event"]

    def test_done_run_brackets_provider_events(self):
        for model, source in (("haiku", "claude"), ("sol", "codex")):
            with self.subTest(model=model):
                shutil.rmtree(self.runs, ignore_errors=True)
                rc, _, _, run = self._dispatch(model)
                self.assertEqual(rc, 0)
                events = read_events(run)
                self.assertEqual([e["seq"] for e in events], list(range(1, len(events) + 1)))
                self.assertEqual(events[0]["source"], "agents-inc")
                self.assertEqual(events[0]["event"], {"type": "run.start", "run_id": run.name, "model": model,
                                                      "kind": source})
                provider = [e for e in events[1:-1]]
                self.assertTrue(provider and all(e["source"] == source for e in provider))
                self.assertEqual(self._ends(run), {"type": "run.end", "outcome": "done", "rc": 0})
                self.assertEqual(stat.S_IMODE((run / "events.jsonl").stat().st_mode), 0o600)

    def test_red_run_ends_red(self):
        rc, _, _, run = self._dispatch("haiku", env={"FAKE_RC": "1"})
        self.assertNotEqual(rc, 0)
        self.assertEqual(self._ends(run), {"type": "run.end", "outcome": "red", "rc": 1})

    def test_launch_failure_ends_launch_failed(self):
        with mock.patch.object(dispatch, "launch", side_effect=OSError("no exec")):
            rc, _, _ = self._main("--slots", str(self._slots()), "--model", "haiku", "--cwd", str(self.repo),
                                  "--run-dir", str(self.runs))
        self.assertNotEqual(rc, 0)
        run = self._run_dir()
        self.assertEqual(self._kinds(run), [("agents-inc", "run.start"), ("agents-inc", "run.end")])
        self.assertEqual(self._ends(run)["outcome"], "launch-failed")

    def test_lint_refusal_ends_refused(self):
        with mock.patch.object(dispatch, "lint_prompt", return_value=([12], "")):
            rc, _, _ = self._main("--slots", str(self._slots()), "--model", "haiku", "--cwd", str(self.repo),
                                  "--run-dir", str(self.runs))
        self.assertEqual(rc, 3)
        run = self._run_dir()
        self.assertEqual(self._kinds(run), [("agents-inc", "run.start"), ("agents-inc", "run.end")])
        self.assertEqual(self._ends(run)["outcome"], "refused")

    def test_dry_run_ends_dry_run(self):
        rc, _, _ = self._main("--slots", str(self._slots()), "--model", "haiku", "--cwd", str(self.repo),
                              "--run-dir", str(self.runs), "--dry-run")
        self.assertEqual(rc, 0)
        run = self._run_dir()
        self.assertEqual(self._kinds(run), [("agents-inc", "run.start"), ("agents-inc", "run.end")])
        self.assertEqual(self._ends(run)["outcome"], "dry-run")

    def test_lead_run_writes_lifecycle_events_only(self):
        seen = {}

        def fake(*a, **k):
            seen["lead"] = k.get("lead_dir")
            return {"rc": 0, "stdout": "", "stderr": "", "argv": [], "session_id": None}
        slots = self._slots(ALLOWLIST="luna, haiku", FAN_OUT="width 1, total 2, depth 1",
                            ROLE="Workhorse terra, dispatched by CoS (opus) in repo.")
        with mock.patch.object(dispatch, "launch", side_effect=fake):
            self._main("--slots", str(slots), "--model", "terra", "--cwd", str(self.repo), "--run-dir", str(self.runs))
        self.assertIsNotNone(seen.get("lead"))
        shutil.rmtree(seen["lead"], ignore_errors=True)
        types = self._kinds(self._run_dir())
        self.assertEqual(types[0], ("agents-inc", "run.start"))
        self.assertEqual(types[-1][1], "run.end")
        self.assertEqual({source for source, _ in types}, {"agents-inc"})

    def test_run_dir_line_on_stderr(self):
        _, _, err, run = self._dispatch("haiku")
        lines = [ln for ln in err.splitlines() if ln.startswith("agents-inc dispatch: run ")]
        self.assertEqual(lines, [f"agents-inc dispatch: run {run.name} dir {run}"])
        self.assertTrue(os.path.isabs(str(run)))

    def test_events_stay_out_of_the_mirror_and_run_json(self):
        home = self.root / "home-repo"
        home.mkdir()
        with mock.patch.dict(os.environ, {"AGENTS_INC_HOME_REPO": str(home)}):
            rc, _, _, run = self._dispatch("haiku")
        self.assertEqual(rc, 0)
        mirrored = list((home / "specs/consumers").glob("*/runs/*"))
        self.assertEqual(len(mirrored), 1)
        self.assertTrue((mirrored[0] / "run.json").is_file())
        self.assertEqual(sorted(p.name for p in mirrored[0].iterdir() if "event" in p.name), [])
        self.assertNotIn("run.start", (run / "run.json").read_text(encoding="utf-8"))
        self.assertNotIn("events_error", json.loads((run / "run.json").read_text(encoding="utf-8")))

    def test_sink_failure_is_recorded_not_fatal(self):
        class Broken(EventSink):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                self.error, self._fd = "OSError: disk full", None
        with mock.patch.object(dispatch, "EventSink", Broken):
            rc, _, _, run = self._dispatch("haiku")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads((run / "run.json").read_text(encoding="utf-8"))["events_error"], "OSError: disk full")

    def _grows_then_times_out(self, model: str, source: str):
        """The fake prints one line and sleeps: the file holds it while dispatch still waits, then the turn deadline fires."""
        box: dict = {}
        env = {"FAKE_SLEEP": "1", "AGENTS_INC_TURN_TIMEOUT_S": "4"}
        worker = threading.Thread(target=lambda: box.update(result=self._dispatch(model, env=env)))
        worker.start()
        seen = False
        deadline = time.monotonic() + 3.5
        while time.monotonic() < deadline and not seen:
            for path in self.runs.glob("*/events.jsonl") if self.runs.exists() else ():
                text = path.read_text(encoding="utf-8")
                seen = f'"source": "{source}"' in text
            time.sleep(0.05)
        alive = worker.is_alive()
        worker.join(30)
        self.assertTrue(seen, "no provider event while the delegate was still running")
        self.assertTrue(alive, "dispatch ended before the delegate was killed")
        rc, _, _, run = box["result"]
        self.assertNotEqual(rc, 0)
        self.assertEqual(self._ends(run), {"type": "run.end", "outcome": "timeout", "rc": 124})

    def test_claude_events_land_before_exit_and_timeout_ends_timeout(self):
        self._grows_then_times_out("haiku", "claude")

    def test_codex_events_land_before_exit_and_timeout_ends_timeout(self):
        self._grows_then_times_out("sol", "codex")


def setUpModule():
    golden_setup()


def tearDownModule():
    golden_teardown()


if __name__ == "__main__":
    unittest.main()
