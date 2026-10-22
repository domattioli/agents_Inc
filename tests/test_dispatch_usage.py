"""Delegate token usage is kept from the claude -p JSON payload and fills ledger append defaults."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agents_inc import host_ledger, ledger
from agents_inc.install.dispatch import claude_usage

PAYLOAD = {"result": "ok", "session_id": "s", "total_cost_usd": 0.5, "num_turns": 3, "duration_ms": 900,
           "modelUsage": {
               "claude-opus-5-5": {"inputTokens": 100, "outputTokens": 20, "cacheReadInputTokens": 1000,
                                   "cacheCreationInputTokens": 50, "costUSD": 0.4},
               "claude-haiku-5-5": {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 0,
                                    "cacheCreationInputTokens": 7, "costUSD": 0.1}}}


class ClaudeUsageTest(unittest.TestCase):
    def test_sums_models_and_keeps_split(self):
        u = claude_usage(PAYLOAD)
        self.assertEqual((u["input_tokens"], u["output_tokens"], u["cache_read"], u["cache_write"]),
                         (110, 25, 1000, 57))
        self.assertEqual(u["num_turns"], 3)
        self.assertEqual(u["cost_usd_list"], 0.5)
        self.assertEqual(set(u["models"]), {"claude-opus-5-5", "claude-haiku-5-5"})

    def test_missing_or_bad_is_none(self):
        self.assertIsNone(claude_usage({"result": "ok"}))
        self.assertIsNone(claude_usage("not a dict"))
        self.assertIsNone(claude_usage({"modelUsage": {}}))

    def test_unknown_field_stays_none_not_zero(self):
        u = claude_usage({"modelUsage": {"m": {"inputTokens": 3}}})
        self.assertEqual(u["input_tokens"], 3)
        self.assertIsNone(u["output_tokens"])


class LedgerAppendDefaultsTest(unittest.TestCase):
    def test_append_fills_tokens_from_usage_json(self):
        with TemporaryDirectory() as d:
            state, ws, rid = Path(d) / "state", Path(d) / "ws", "20261022T000000Z-haiku-abc123"
            (state / "dispatch-runs" / rid).mkdir(parents=True)
            (state / "dispatch-runs" / rid / "usage.json").write_text(json.dumps(claude_usage(PAYLOAD)))
            rc = host_ledger.cli(["append", "--workspace", str(ws), "--run-id", rid, "--verdict", "pass"], state)
            self.assertEqual(rc, 0)
            rows = [json.loads(l) for l in (ws / ".workerbees" / "ledger.jsonl").read_text().splitlines()]
            self.assertEqual((rows[-1]["input_tokens"], rows[-1]["output_tokens"], rows[-1]["cache_read"]),
                             (110, 25, 1000))

    def test_explicit_flag_wins(self):
        with TemporaryDirectory() as d:
            state, ws, rid = Path(d) / "state", Path(d) / "ws", "r1"
            (state / "dispatch-runs" / rid).mkdir(parents=True)
            (state / "dispatch-runs" / rid / "usage.json").write_text(json.dumps(claude_usage(PAYLOAD)))
            host_ledger.cli(["append", "--workspace", str(ws), "--run-id", rid, "--verdict", "pass",
                             "--input-tokens", "7"], state)
            row = json.loads((ws / ".workerbees" / "ledger.jsonl").read_text().splitlines()[-1])
            self.assertEqual(row["input_tokens"], 7)


if __name__ == "__main__":
    unittest.main()
