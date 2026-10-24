"""Spec 027: rendering, following and redacting live delegate events (agents_inc/live_rows.py)."""
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agents_inc import live_rows

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "live-events"
BASE = 1_000_000.0
NO_ENV: dict = {}
NO_HOME = "/nonexistent-home"


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def envelope(seq, epoch, source, event, **extra):
    return {"v": 1, "seq": seq, "ts": iso(epoch), "source": source, "event": event, **extra}


def fixture_envelopes(name: str, source: str, model: str, run_id: str = "fixture-run") -> list:
    """run.start at second 0, fixture line N at second N, run.end at second N+1 (fixtures/live-events/README.md)."""
    out = [envelope(1, BASE, "agents-inc", {"type": "run.start", "run_id": run_id, "model": model, "kind": source})]
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    for n, text in enumerate(lines, start=1):
        try:
            event = json.loads(text)
        except ValueError:
            event = None
        out.append(envelope(n + 1, BASE + n, source, event if isinstance(event, dict) else {"type": "raw", "text": text}))
    out.append(envelope(len(lines) + 2, BASE + len(lines) + 1, "agents-inc", {"type": "run.end", "outcome": "done", "rc": 0}))
    return out


def render_all(envelopes: list, model: str) -> list:
    rows = []
    for env in envelopes:
        rows.extend(live_rows.render(env, model, BASE, env=NO_ENV, home=NO_HOME))
    return rows


class RenderFixtureTest(unittest.TestCase):
    def check(self, jsonl, source, model, rows_file):
        expected = (FIXTURES / rows_file).read_text(encoding="utf-8").splitlines()
        self.assertEqual(render_all(fixture_envelopes(jsonl, source, model), model), expected)

    def test_codex_fixture_rows(self):
        self.check("codex.jsonl", "codex", "sol", "codex.rows.txt")

    def test_claude_fixture_rows(self):
        self.check("claude.jsonl", "claude", "haiku", "claude.rows.txt")


class RenderRulesTest(unittest.TestCase):
    def one(self, source, event, model="sol", at=0.0, **kw):
        return live_rows.render(envelope(1, BASE + at, source, event), model, BASE, env=NO_ENV, home=NO_HOME, **kw)

    def test_row_over_240_chars_is_cut_to_239_plus_ellipsis(self):
        (row,) = self.one("codex", {"type": "item.completed", "item": {"type": "agent_message", "text": "word " * 200}})
        self.assertEqual(len(row), 240)
        self.assertTrue(row.endswith("…"))

    def test_think_summary_is_cut_to_120_chars(self):
        (row,) = self.one("codex", {"type": "item.completed", "item": {"type": "reasoning", "text": "a" * 400}})
        self.assertEqual(row, "[00:00] sol think: " + "a" * 120)

    def test_whitespace_collapses(self):
        (row,) = self.one("codex", {"type": "item.completed", "item": {"type": "agent_message", "text": "a\n\n  b\t c"}})
        self.assertEqual(row, "[00:00] sol say: a b c")

    def test_clock_counts_minutes_and_seconds(self):
        (row,) = self.one("codex", {"type": "turn.started"}, at=125.9)
        self.assertTrue(row.startswith("[02:05] "), row)

    def test_unknown_type_row_has_source_and_type_only(self):
        (row,) = self.one("claude", {"type": "mystery", "payload": {"secret": "x" * 30}}, model="haiku")
        self.assertEqual(row, "[00:00] haiku note: claude mystery")

    def test_raw_row_shows_first_120_chars(self):
        (row,) = self.one("codex", {"type": "raw", "text": "z" * 300})
        self.assertEqual(row, "[00:00] sol note: codex raw: " + "z" * 120)

    def test_error_result_is_an_error_row(self):
        (row,) = self.one("claude", {"type": "result", "is_error": True, "result": "boom"}, model="haiku")
        self.assertEqual(row, "[00:00] haiku error: boom")

    def test_turn_failed_is_an_error_row(self):
        (row,) = self.one("codex", {"type": "turn.failed", "error": {"message": "no quota"}})
        self.assertEqual(row, "[00:00] sol error: no quota")

    def test_claude_message_with_two_blocks_gives_two_rows(self):
        event = {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "hi"}, {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}}
        self.assertEqual(self.one("claude", event, model="haiku"),
                         ["[00:00] haiku say: hi", "[00:00] haiku tool: ls"])

    def test_run_end_row(self):
        (row,) = self.one("agents-inc", {"type": "run.end", "outcome": "timeout", "rc": 124})
        self.assertEqual(row, "[00:00] sol end: timeout rc=124")

    def test_events_truncated_is_a_note(self):
        (row,) = self.one("agents-inc", {"type": "events.truncated", "cap_bytes": 5})
        self.assertEqual(row, "[00:00] sol note: agents-inc events.truncated")


class FakeClock:
    """now()/sleep() on a fake timeline; sleep fires the scheduled (time, callback) pairs that fell due."""

    def __init__(self, schedule=()):
        self.t = 0.0
        self.schedule = sorted(schedule, key=lambda item: item[0])

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds
        while self.schedule and self.schedule[0][0] <= self.t + 1e-9:
            self.schedule.pop(0)[1]()


class TimedOut:
    """A stand-in for stdout that remembers when each write happened on the fake clock."""

    def __init__(self, clock):
        self.clock, self.writes = clock, []

    def write(self, text):
        self.writes.append((self.clock.t, text))

    def flush(self):
        pass

    @property
    def text(self):
        return "".join(t for _, t in self.writes)


def append_lines(path: Path, envelopes: list, cut_last_at: int | None = None):
    data = "".join(json.dumps(e) + "\n" for e in envelopes)
    if cut_last_at is not None:
        data = data[:cut_last_at]
    with open(path, "ab") as fh:
        fh.write(data.encode("utf-8"))


def codex_say(seq, at, text="hello"):
    return envelope(seq, BASE + at, "codex", {"type": "item.completed", "item": {"type": "agent_message", "text": text}})


def run_start():
    return envelope(1, BASE, "agents-inc", {"type": "run.start", "run_id": "r", "model": "sol", "kind": "codex"})


def run_end(seq, at):
    return envelope(seq, BASE + at, "agents-inc", {"type": "run.end", "outcome": "done", "rc": 0})


class FollowTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = Path(self._tmp.name)
        self.events = self.run_dir / "events.jsonl"

    def follow(self, clock, **kw):
        out = TimedOut(clock)
        rc = live_rows.follow(self.run_dir, out, clock, env=NO_ENV, home=NO_HOME, **kw)
        return rc, out

    def test_partial_last_line_is_held_until_complete(self):
        line = json.dumps(codex_say(2, 1, "whole")) + "\n"
        half = len(line) // 2
        append_lines(self.events, [run_start()])
        with open(self.events, "ab") as fh:
            fh.write(line[:half].encode())

        def finish_line():
            with open(self.events, "ab") as fh:
                fh.write(line[half:].encode())
            append_lines(self.events, [run_end(3, 2)])
        clock = FakeClock([(0.6, finish_line)])
        rc, out = self.follow(clock)
        self.assertEqual(rc, 0)
        say_at = [t for t, text in out.writes if "say: whole" in text]
        self.assertEqual(len(say_at), 1)
        self.assertGreaterEqual(say_at[0], 0.6)

    def test_first_batch_is_prompt_and_the_next_waits_for_one_second(self):
        append_lines(self.events, [run_start(), codex_say(2, 1)])
        clock = FakeClock([(0.2, lambda: append_lines(self.events, [codex_say(3, 2, "second")])),
                           (3.0, lambda: append_lines(self.events, [run_end(4, 4)]))])
        rc, out = self.follow(clock)
        self.assertEqual(rc, 0)
        self.assertEqual(out.writes[0][0], 0.0)
        second = [t for t, text in out.writes if "second" in text]
        self.assertEqual(len(second), 1)
        self.assertGreaterEqual(second[0], 1.0)  # the 0.2 s write waited for the 1 s flush window
        self.assertLess(second[0], 1.5)

    def test_twenty_waiting_rows_flush_at_once_and_batches_end_with_an_empty_line(self):
        append_lines(self.events, [run_start()] + [codex_say(n, n, f"m{n}") for n in range(2, 47)])
        clock = FakeClock([(1.5, lambda: append_lines(self.events, [run_end(47, 50)]))])
        rc, out = self.follow(clock)
        self.assertEqual(rc, 0)
        batches = [b for b in out.text.split("\n\n") if b]
        # 1 start + 45 say = 46 rows at t=0 (20, 20, then 6 wait for the window); run.end lands later as its own batch
        self.assertEqual([len(b.splitlines()) for b in batches], [20, 20, 6, 1])
        self.assertEqual([t for t, _ in out.writes][:2], [0.0, 0.0])

    def test_exit_0_after_run_end_and_tail_is_flushed(self):
        append_lines(self.events, [run_start(), codex_say(2, 1), run_end(3, 2)])
        rc, out = self.follow(FakeClock())
        self.assertEqual(rc, 0)
        self.assertIn("sol end: done rc=0", out.text)

    def test_exit_3_when_no_file_appears_within_30_seconds(self):
        clock = FakeClock()
        rc, out = self.follow(clock)
        self.assertEqual(rc, 3)
        self.assertGreaterEqual(clock.t, 30.0)
        self.assertLess(clock.t, 31.0)
        self.assertEqual(out.text, "")

    def test_a_file_that_appears_late_is_followed(self):
        clock = FakeClock([(5.0, lambda: append_lines(self.events, [run_start(), run_end(2, 1)]))])
        rc, out = self.follow(clock)
        self.assertEqual(rc, 0)
        self.assertIn("sol start: run r", out.text)

    def test_first_row_within_two_seconds_of_the_first_event_at_half_second_pace(self):
        """SC-001."""
        schedule = [(0.0, lambda: append_lines(self.events, [run_start()]))]
        schedule += [(0.5 * n, (lambda n=n: append_lines(self.events, [codex_say(n + 1, 0.5 * n, f"e{n}")])))
                     for n in range(1, 8)]
        schedule.append((4.0, lambda: append_lines(self.events, [run_end(20, 4)])))
        clock = FakeClock(schedule)
        clock.sleep(0)  # fire the t=0 write
        rc, out = self.follow(clock)
        self.assertEqual(rc, 0)
        first_event_at = 0.0
        self.assertLessEqual(out.writes[0][0] - first_event_at, 2.0)


class EventsCommandTest(unittest.TestCase):
    """`agents-inc events follow|redact` (FR-013), run as the CLI does."""

    def run_cli(self, *args, stdin="", env=None):
        import os
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as home:
            full = dict(os.environ, HOME=home, PYTHONPATH=str(FIXTURES.parents[1]))
            full.update(env or {})
            return subprocess.run([sys.executable, "-m", "agents_inc.install.cli", "events", *args], input=stdin,
                                  capture_output=True, text=True, env=full, timeout=60, cwd=home)

    def test_follow_prints_rows_of_a_finished_run_and_exits_0(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            append_lines(Path(tmp) / "events.jsonl", fixture_envelopes("codex.jsonl", "codex", "sol"))
            done = self.run_cli("follow", tmp)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("[00:04] sol tool: rg -n \"launch\" agents_inc", done.stdout)
        self.assertIn("sol end: done rc=0", done.stdout)
        self.assertNotIn("sk-testABCDEFGHIJKLMNOPQRST", done.stdout)

    def test_redact_filters_stdin(self):
        done = self.run_cli("redact", stdin="key ghp_abcdefghijklmnopqrstuvwx and MYVAL12345678 end\n",
                            env={"DEMO_API_KEY": "MYVAL12345678"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, "key [redacted] and [redacted] end\n")

    def test_follow_needs_a_run_dir(self):
        self.assertEqual(self.run_cli("follow").returncode, 2)


class RedactTest(unittest.TestCase):
    PLANTED = ("sk-testABCDEFGHIJKLMNOPQRST", "ghp_abcdefghijklmnopqrstuvwx", "api_key=0123456789ab", "0123456789ab")

    def test_secret_re_matches_become_redacted(self):
        text = "a sk-testABCDEFGHIJKLMNOPQRST b ghp_abcdefghijklmnopqrstuvwx c password: hunter2hunter2"
        self.assertEqual(live_rows.redact(text, {}, NO_HOME), "a [redacted] b [redacted] c [redacted]")

    def test_env_values_of_secret_named_variables_are_redacted(self):
        env = {"MY_KEY": "abcdefgh1", "SOME_TOKEN": "tok-12345678", "DB_PASSWORD": "pw-12345678", "X_SECRET": "sec-12345678",
               "PLAIN": "plainvalue99", "SHORT_KEY": "short"}
        text = "abcdefgh1 tok-12345678 pw-12345678 sec-12345678 plainvalue99 short"
        self.assertEqual(live_rows.redact(text, env, NO_HOME),
                         "[redacted] [redacted] [redacted] [redacted] plainvalue99 short")

    def test_home_directory_becomes_tilde(self):
        self.assertEqual(live_rows.redact("see /Users/dom/proj/a.py", {}, "/Users/dom"), "see ~/proj/a.py")

    def test_no_planted_secret_survives_in_any_fixture_row(self):
        for name, source, model in (("codex.jsonl", "codex", "sol"), ("claude.jsonl", "claude", "haiku")):
            joined = "\n".join(render_all(fixture_envelopes(name, source, model), model))
            for secret in self.PLANTED:
                self.assertNotIn(secret, joined, f"{secret} leaked from {name}")

    def test_secret_in_unknown_event_payload_never_reaches_a_row(self):
        env = envelope(1, BASE, "codex", {"type": "weird", "payload": "sk-testABCDEFGHIJKLMNOPQRST"})
        self.assertNotIn("sk-test", "".join(live_rows.render(env, "sol", BASE, env={}, home=NO_HOME)))


if __name__ == "__main__":
    unittest.main()
