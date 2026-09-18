import subprocess
import sys
import unittest


class AgentsIncCompatibilityTests(unittest.TestCase):
    def test_workerbees_namespace_forwards_to_canonical_implementation(self):
        import agents_inc
        from agents_inc.router import Route
        from workerbees.router import Route as WorkerbeesRoute

        self.assertTrue(agents_inc.__path__)
        self.assertIs(Route, WorkerbeesRoute)

    def test_cli_entrypoint_is_available_under_new_namespace(self):
        result = subprocess.run(
            [sys.executable, "-m", "agents_inc.install.cli", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("agents-inc", result.stdout)


if __name__ == "__main__":
    unittest.main()
