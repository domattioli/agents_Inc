"""free_health.report() must not lose counts under concurrent writers."""
import json
import multiprocessing as mp
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _worker(home, n):
    os.environ["HOME"] = home
    sys.path.insert(0, str(ROOT))
    from agents_inc import free_health
    for _ in range(n):
        free_health.report("p", "m", "ok")


@unittest.skipIf(os.name != "posix", "flock lock is POSIX only")
class TestFreeHealthConcurrentReport(unittest.TestCase):
    def test_parallel_reports_keep_every_count(self):
        with tempfile.TemporaryDirectory() as home:
            ctx = mp.get_context("spawn")
            procs = [ctx.Process(target=_worker, args=(home, 50)) for _ in range(4)]
            for p in procs:
                p.start()
            for p in procs:
                p.join(60)
                self.assertEqual(p.exitcode, 0)
            stats = json.loads((Path(home) / ".codex-bridge" / "rate-limit-stats.json").read_text())
            self.assertEqual(stats["p/m"]["calls_total"], 200)


if __name__ == "__main__":
    unittest.main()
