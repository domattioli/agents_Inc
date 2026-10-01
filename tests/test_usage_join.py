"""Spec 016 FR-003 (#36): read-only join from ledger nodes to usage.db rows.

Supervisor-owned acceptance tests. Generated temp databases only; never opens ~/.codex-bridge.
"""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from agents_inc import usage_join

SCHEMA = """CREATE TABLE usage(uid TEXT PRIMARY KEY, ts TEXT NOT NULL, day TEXT NOT NULL, backend TEXT NOT NULL,
model TEXT, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, cache_read INTEGER DEFAULT 0,
cache_write INTEGER DEFAULT 0, reasoning INTEGER DEFAULT 0)"""


def row(node_id, status, ts, provider=None, model=None, run_id=None):
    return {"id": node_id, "run_id": run_id, "model": model, "tier": None, "task": None, "provider": provider,
            "parent_id": None, "edge_type": None, "status": status, "seconds": None, "subscription_calls": None,
            "gate_reason": None, "timestamp": ts}


class UsageJoinTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name) / "ws"
        (self.ws / ".workerbees").mkdir(parents=True)
        self.db = Path(self.tmp.name) / "usage.db"
        conn = sqlite3.connect(str(self.db))
        conn.execute(SCHEMA)
        rows = [
            ("u1", "2026-10-01T12:00:10+00:00", "gemini", "gemini-flash-lite-latest", 100, 10, 0, 0),
            ("u2", "2026-10-01T12:00:20+00:00", "gemini", "gemini-flash-lite-latest", 200, 20, 5, 1),
            ("u3", "2026-10-01T13:00:00+00:00", "gemini", "gemini-flash-lite-latest", 999, 99, 0, 0),
            ("u4", "2026-10-01T12:00:15+00:00", "codex", "gpt-5.6-luna", 50, 5, 0, 0),
            ("u5", "2026-10-01T12:00:15+00:00", "claude", "claude-haiku-4-5", 70, 7, 0, 0),
        ]
        conn.executemany("INSERT INTO usage(uid, ts, day, backend, model, input_tokens, output_tokens, cache_read, "
                         "cache_write) VALUES (?,?,'2026-10-01',?,?,?,?,?,?)", rows)
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def ledger(self, *rows):
        with (self.ws / ".workerbees" / "ledger.jsonl").open("w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    def test_window_match_sums_rows(self):
        self.ledger(row("g1", "dispatched", "2026-10-01T12:00:00.000000Z", "gemini", "gemini-flash-lite-latest", "r"),
                    row("g1", "verified", "2026-10-01T12:00:30.000000Z"))
        got = usage_join.usage_for(self.ws, "g1", db_path=self.db)
        self.assertIsNotNone(got)
        self.assertEqual((got["input_tokens"], got["output_tokens"], got["cache_read"], got["cache_write"]),
                         (300, 30, 5, 1))
        self.assertEqual(got["rows"], 2)
        self.assertEqual(got["match"], "time-window")

    def test_codex_nickname_matches_slug(self):
        self.ledger(row("c1", "dispatched", "2026-10-01T12:00:00.000000Z", "codex", "luna", "r"),
                    row("c1", "verified", "2026-10-01T12:00:30.000000Z"))
        got = usage_join.usage_for(self.ws, "c1", db_path=self.db)
        self.assertEqual((got["input_tokens"], got["output_tokens"]), (50, 5))

    def test_missing_db_is_unknown_and_not_created(self):
        self.ledger(row("g1", "dispatched", "2026-10-01T12:00:00.000000Z", "gemini", "gemini-flash-lite-latest", "r"),
                    row("g1", "verified", "2026-10-01T12:00:30.000000Z"))
        absent = Path(self.tmp.name) / "absent.db"
        self.assertIsNone(usage_join.usage_for(self.ws, "g1", db_path=absent))
        self.assertFalse(absent.exists())

    def test_no_matching_rows_is_unknown(self):
        self.ledger(row("m1", "dispatched", "2026-10-01T12:00:00.000000Z", "mistral", "mistral-small-latest", "r"),
                    row("m1", "verified", "2026-10-01T12:00:30.000000Z"))
        self.assertIsNone(usage_join.usage_for(self.ws, "m1", db_path=self.db))

    def test_claude_provider_is_unknown(self):
        self.ledger(row("h1", "dispatched", "2026-10-01T12:00:00.000000Z", "claude", "claude-haiku-4-5", "r"),
                    row("h1", "verified", "2026-10-01T12:00:30.000000Z"))
        self.assertIsNone(usage_join.usage_for(self.ws, "h1", db_path=self.db))

    def test_no_return_row_is_unknown(self):
        self.ledger(row("g1", "dispatched", "2026-10-01T12:00:00.000000Z", "gemini", "gemini-flash-lite-latest", "r"))
        self.assertIsNone(usage_join.usage_for(self.ws, "g1", db_path=self.db))

    def test_unknown_node_is_unknown(self):
        self.ledger(row("g1", "dispatched", "2026-10-01T12:00:00.000000Z", "gemini", "gemini-flash-lite-latest", "r"))
        self.assertIsNone(usage_join.usage_for(self.ws, "nope", db_path=self.db))

    def test_overlapping_same_model_node_is_ambiguous(self):
        self.ledger(row("g1", "dispatched", "2026-10-01T12:00:00.000000Z", "gemini", "gemini-flash-lite-latest", "r"),
                    row("g2", "dispatched", "2026-10-01T12:00:05.000000Z", "gemini", "gemini-flash-lite-latest", "r"),
                    row("g1", "verified", "2026-10-01T12:00:30.000000Z"),
                    row("g2", "verified", "2026-10-01T12:00:40.000000Z"))
        self.assertIsNone(usage_join.usage_for(self.ws, "g1", db_path=self.db))

    def test_host_hook_row_is_unknown(self):
        d = row("g1", "dispatched", "2026-10-01T12:00:00.000000Z", "gemini", "gemini-flash-lite-latest", "r")
        d["source"] = "host-hook"
        self.ledger(d, row("g1", "verified", "2026-10-01T12:00:30.000000Z"))
        self.assertIsNone(usage_join.usage_for(self.ws, "g1", db_path=self.db))

    def test_timestamps_compare_as_datetimes_not_strings(self):
        conn = sqlite3.connect(str(self.db))
        conn.execute("INSERT INTO usage(uid, ts, day, backend, model, input_tokens, output_tokens) VALUES "
                     "('u6', '2026-10-01T08:00:25-04:00', '2026-10-01', 'mistral', 'mistral-small-latest', 40, 4), "
                     "('u7', '2026-10-01T12:00:30.500000+00:00', '2026-10-01', 'mistral', 'mistral-small-latest', 9, 9)")
        conn.commit()
        conn.close()
        self.ledger(row("m1", "dispatched", "2026-10-01T12:00:00.000000Z", "mistral", "mistral-small-latest", "r"),
                    row("m1", "verified", "2026-10-01T12:00:30.000000Z"))
        got = usage_join.usage_for(self.ws, "m1", db_path=self.db)
        self.assertIsNotNone(got)  # 08:00:25-04:00 is 12:00:25Z, inside the window
        self.assertEqual((got["input_tokens"], got["rows"]), (40, 1))  # 12:00:30.5 is after the window end

    def test_naive_usage_timestamp_is_read_as_utc(self):
        conn = sqlite3.connect(str(self.db))
        conn.execute("INSERT INTO usage(uid, ts, day, backend, model, input_tokens, output_tokens) VALUES "
                     "('u8', '2026-10-01T12:00:12', '2026-10-01', 'mistral', 'mistral-small-latest', 8, 1), "
                     "('u9', '2026-10-01T12:00:14+00:00', '2026-10-01', 'mistral', 'mistral-small-latest', 2, 1)")
        conn.commit()
        conn.close()
        self.ledger(row("m1", "dispatched", "2026-10-01T12:00:00.000000Z", "mistral", "mistral-small-latest", "r"),
                    row("m1", "verified", "2026-10-01T12:00:30.000000Z"))
        got = usage_join.usage_for(self.ws, "m1", db_path=self.db)
        self.assertIsNotNone(got)
        self.assertEqual((got["input_tokens"], got["rows"]), (10, 2))

    def test_db_bytes_unchanged(self):
        self.ledger(row("g1", "dispatched", "2026-10-01T12:00:00.000000Z", "gemini", "gemini-flash-lite-latest", "r"),
                    row("g1", "verified", "2026-10-01T12:00:30.000000Z"))
        before = self.db.read_bytes()
        usage_join.usage_for(self.ws, "g1", db_path=self.db)
        self.assertEqual(self.db.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
