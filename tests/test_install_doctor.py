import tempfile
import unittest
from pathlib import Path

from agents_inc.install.doctor import check_install
from agents_inc.install.paths import InstallPaths


class DoctorTest(unittest.TestCase):
    def test_missing_receipt_is_not_ready(self):
        with tempfile.TemporaryDirectory() as raw:
            report = check_install(InstallPaths.for_home(Path(raw) / "home"))
            self.assertFalse(report.ready)
            self.assertIn("WB_RELEASE_UNTRUSTED", report.codes)
