"""approval_status must not depend on the machine time zone (W1 #3)."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = r"""
import os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from agents_inc.control import Control
c = Control(Path(tempfile.mkdtemp()))
for hours in (1, -1):
    exp = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")
    a = c.request_approval("r", "u", "act", "res", "h", "low", [], exp)
    print(c.approval_status(a))
"""


class TestApprovalStatusTimeZone(unittest.TestCase):
    def test_status_same_in_every_time_zone(self):
        for tz in ("UTC", "America/New_York", "Asia/Tokyo"):
            env = dict(os.environ, TZ=tz, WORKERBEES_STORE="jsonl", PYTHONPATH=str(ROOT))
            r = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=env,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.split(), ["pending", "expired"], tz)


if __name__ == "__main__":
    unittest.main()
