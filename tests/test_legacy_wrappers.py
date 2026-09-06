import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "codex-bridge" / "scripts"


class LegacyWrapperGovernanceTest(unittest.TestCase):
    def test_all_wrappers_refuse_governed_lanes_before_credentials(self):
        for name in ("gask.sh", "mask.sh", "oask.sh"):
            env = {"PATH": os.environ["PATH"], "WORKERBEES_GOVERNANCE": "shadow"}
            result = subprocess.run(
                [str(SCRIPTS / name), "prompt"], env=env, text=True,
                capture_output=True, timeout=5,
            )
            self.assertEqual(3, result.returncode, name)
            self.assertIn("disabled in governed lanes", result.stderr)

    def test_no_eval_or_paid_and_model_override_escape(self):
        for name in ("gask.sh", "mask.sh", "oask.sh"):
            body = (SCRIPTS / name).read_text()
            self.assertNotIn("eval echo", body)
            self.assertNotIn("OR_ALLOW_PAID", body)
            self.assertNotIn("--model)", body)


if __name__ == "__main__":
    unittest.main()
