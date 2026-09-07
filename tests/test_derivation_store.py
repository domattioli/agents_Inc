"""Unit tests for workerbees/derivation_store.py -- RunRecord persistence + replay.

Covers: lossless persist-then-reload round trip, replay recomputation matching the
originally persisted pick, and an authority_change_events entry round-tripping.
"""
import tempfile
import unittest
from pathlib import Path

from workerbees.lineup_router import RunRecord, route_step, with_authority_change
from workerbees.router import Route
from workerbees.derivation_store import persist_run_record, load_run_record, replay_pick


class TestPersistReloadRoundTrip(unittest.TestCase):
    """Round trip: persist a RunRecord, reload it, expect a lossless copy."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def test_round_trip_is_lossless(self):
        authority = Route(provider="claude", model="sonnet", tier="workhorse", cmd_kind="cli")
        pool = (
            Route(provider="codex", model="gpt-5.6-terra", tier="workhorse", cmd_kind="cli"),
            Route(provider="codex", model="gpt-6-astra", tier="executive", cmd_kind="cli"),
        )
        run = RunRecord(
            run_id="rt-1",
            task="classify",
            accept_rule="matches labeled answer key",
            authority_holder=authority,
            authority_limits={"max_cost_usd": 2},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=("sonnet", "gpt-5.6-terra", "gpt-6-astra"),
            hard_limits={"data": "public_only"},
            budget={"max_cost_usd": 2, "deadline_sec": 120},
            tie_break_order=("cost", "latency"),
            retry_rule={"max_retries": 1, "fallback": "next_candidate"},
            model_snapshot_ref="snap-001",
        )
        run = route_step(run, "start", pool)

        ok = persist_run_record(self.ws, run)
        self.assertTrue(ok)

        reloaded = load_run_record(self.ws, "rt-1")
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded, run, "reload must be a lossless copy of the persisted RunRecord")

    def test_reload_missing_run_id_returns_none(self):
        self.assertIsNone(load_run_record(self.ws, "no-such-run"))

    def test_reload_before_any_persist_returns_none(self):
        empty_ws = Path(tempfile.mkdtemp())
        self.assertIsNone(load_run_record(empty_ws, "rt-1"))

    def test_last_write_for_run_id_wins(self):
        authority = Route(provider="claude", model="sonnet", tier="workhorse", cmd_kind="cli")
        base = RunRecord(
            run_id="rt-2",
            task="classify",
            accept_rule="matches key",
            authority_holder=authority,
            authority_limits={},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=("sonnet",),
            hard_limits={},
            budget={},
            tie_break_order=("cost",),
            retry_rule={"max_retries": 1},
            model_snapshot_ref="snap-001",
        )
        pool = (Route(provider="codex", model="gpt-5.6-terra", tier="workhorse", cmd_kind="cli"),)
        first = route_step(base, "start", pool)
        persist_run_record(self.ws, first)

        pool2 = (Route(provider="codex", model="gpt-6-astra", tier="executive", cmd_kind="cli"),)
        second = route_step(first, "failure", pool2)  # retries within limit -> same pick, retry recorded
        persist_run_record(self.ws, second)

        reloaded = load_run_record(self.ws, "rt-2")
        self.assertEqual(reloaded, second, "last persisted snapshot for a run_id must win on reload")


class TestReplayDeterminism(unittest.TestCase):
    """replay_pick() must recompute the same route that was originally persisted."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def test_replay_matches_persisted_pick_single_step(self):
        authority = Route(provider="claude", model="sonnet", tier="workhorse", cmd_kind="cli")
        pool = (
            Route(provider="codex", model="gpt-5.6-terra", tier="workhorse", cmd_kind="cli"),
            Route(provider="codex", model="gpt-6-astra", tier="executive", cmd_kind="cli"),
        )
        run = RunRecord(
            run_id="replay-1",
            task="classify",
            accept_rule="matches key",
            authority_holder=authority,
            authority_limits={},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=("sonnet", "gpt-5.6-terra", "gpt-6-astra"),
            hard_limits={},
            budget={},
            tie_break_order=("cost",),
            retry_rule={"max_retries": 1},
            model_snapshot_ref="snap-001",
        )
        run = route_step(run, "start", pool)
        self.assertIsNotNone(run.picked)

        persist_run_record(self.ws, run)
        reloaded = load_run_record(self.ws, "replay-1")

        self.assertEqual(replay_pick(reloaded), run.picked,
                          "replay must recompute the same pick from candidates_considered")

    def test_replay_matches_persisted_pick_after_reranking(self):
        """Multiple route_step calls append to candidates_considered; replay must track
        the LATEST kept entry, not the first, to match the run's final persisted pick."""
        authority = Route(provider="claude", model="sonnet", tier="workhorse", cmd_kind="cli")
        pool = (
            Route(provider="codex", model="gpt-5.6-terra", tier="workhorse", cmd_kind="cli"),
            Route(provider="codex", model="gpt-6-astra", tier="executive", cmd_kind="cli"),
        )
        run = RunRecord(
            run_id="replay-2",
            task="classify",
            accept_rule="matches key",
            authority_holder=authority,
            authority_limits={},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=("sonnet", "gpt-5.6-terra", "gpt-6-astra"),
            hard_limits={},
            budget={},
            tie_break_order=("cost",),
            retry_rule={"max_retries": 0},  # zero retries -> failure re-ranks immediately
            model_snapshot_ref="snap-001",
        )
        run = route_step(run, "start", pool)
        first_pick = run.picked
        run = route_step(run, "failure", pool)  # first candidate removed, re-ranks to the other
        self.assertNotEqual(run.picked, first_pick)

        persist_run_record(self.ws, run)
        reloaded = load_run_record(self.ws, "replay-2")

        self.assertEqual(replay_pick(reloaded), run.picked)
        self.assertNotEqual(replay_pick(reloaded), first_pick)

    def test_replay_empty_pool_returns_none(self):
        authority = Route(provider="claude", model="sonnet", tier="workhorse", cmd_kind="cli")
        run = RunRecord(
            run_id="replay-empty",
            task="classify",
            accept_rule="matches key",
            authority_holder=authority,
            authority_limits={},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=("sonnet",),
            hard_limits={},
            budget={},
            tie_break_order=("cost",),
            retry_rule={"max_retries": 1},
            model_snapshot_ref="snap-001",
        )
        # Never route_step'd -- candidates_considered is empty, picked is None.
        persist_run_record(self.ws, run)
        reloaded = load_run_record(self.ws, "replay-empty")
        self.assertIsNone(reloaded.picked)
        self.assertIsNone(replay_pick(reloaded))


class TestAuthorityChangeEventRoundTrip(unittest.TestCase):
    """A RunRecord carrying an authority_change_events entry must round-trip that
    event's from/to/reason fields intact."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def test_authority_change_event_round_trips(self):
        old_authority = Route(provider="claude", model="haiku", tier="grunt", cmd_kind="cli")
        new_authority = Route(provider="claude", model="sonnet", tier="workhorse", cmd_kind="cli")

        run = RunRecord(
            run_id="ace-1",
            task="classify",
            accept_rule="matches key",
            authority_holder=old_authority,
            authority_limits={},
            authority_movable=True,
            authority_move_rule="backup_list",
            policy_version="2026-09-05.1",
            allowed_models=("haiku", "sonnet"),
            hard_limits={},
            budget={},
            tie_break_order=("cost",),
            retry_rule={"max_retries": 1},
            model_snapshot_ref="snap-001",
        )
        run = with_authority_change(run, frm=old_authority, to=new_authority,
                                     reason="holder_cannot_continue")

        self.assertEqual(len(run.authority_change_events), 1)

        persist_run_record(self.ws, run)
        reloaded = load_run_record(self.ws, "ace-1")

        self.assertEqual(reloaded.authority_holder, new_authority)
        self.assertEqual(len(reloaded.authority_change_events), 1)
        event = reloaded.authority_change_events[0]
        self.assertEqual(event["from"], {"provider": "claude", "model": "haiku",
                                          "tier": "grunt", "cmd_kind": "cli"})
        self.assertEqual(event["to"], {"provider": "claude", "model": "sonnet",
                                        "tier": "workhorse", "cmd_kind": "cli"})
        self.assertEqual(event["reason"], "holder_cannot_continue")
        self.assertEqual(reloaded, run, "full RunRecord equality must hold post round-trip")


if __name__ == "__main__":
    unittest.main()
