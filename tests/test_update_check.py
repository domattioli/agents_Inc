"""Update notice: version compare, daily cache, opt-out, silent failure. No network."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents_inc import __version__
from agents_inc.install import update_check as uc


class UpdateCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_newer(self):
        self.assertTrue(uc.newer("0.3.10", "0.3.9"))
        self.assertTrue(uc.newer("0.4.0", "0.4.0rc1"))
        self.assertFalse(uc.newer("0.3.1", "0.3.1"))
        self.assertFalse(uc.newer("0.3.0", "0.3.1"))
        self.assertFalse(uc.newer("garbage", "0.3.1"))

    def test_notice_and_daily_cache(self):
        calls = []

        def fetch(timeout):
            calls.append(timeout)
            return "99.0.0"
        text = uc.notice(self.state, env={}, fetch=fetch, now=1000.0)
        self.assertIn("agents-inc 99.0.0 is available", text)
        self.assertIn(__version__, text)
        uc.notice(self.state, env={}, fetch=fetch, now=1000.0 + 3600)
        self.assertEqual(len(calls), 1)  # cached within a day
        uc.notice(self.state, env={}, fetch=fetch, now=1000.0 + uc.TTL_S + 1)
        self.assertEqual(len(calls), 2)

    def test_same_version_failure_and_opt_out_are_silent(self):
        self.assertEqual(uc.notice(self.state, env={}, fetch=lambda t: __version__), "")
        self.tmp.cleanup(); self.tmp = tempfile.TemporaryDirectory(); self.state = Path(self.tmp.name)

        def boom(timeout):
            raise OSError("offline")
        self.assertEqual(uc.notice(self.state, env={}, fetch=boom), "")
        called = []
        self.assertEqual(uc.notice(self.state, env={uc.OPT_OUT: "1"}, fetch=lambda t: called.append(1) or "99.0.0"), "")
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
