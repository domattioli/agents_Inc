import json, tempfile, unittest
from pathlib import Path
from workerbees.router import Route
from workerbees.policy import check_dispatch, is_authorized, PolicyError, paused

class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def test_unauthorized_workspace_blocks_confidential_to_optional(self):
        r = Route("gemini", "gemini-2.5-flash", "cheap", "http")
        with self.assertRaises(PolicyError):
            check_dispatch(r, self.ws, confidential=True)

    def test_required_provider_always_ok(self):
        r = Route("claude", "haiku", "cheap", "cli")
        check_dispatch(r, self.ws, confidential=True)

    def test_authorization_file_grants(self):
        (self.ws / ".workerbees").mkdir()
        (self.ws / ".workerbees" / "authorization.json").write_text(json.dumps(
            {"optional_providers": True, "granted_by": "dom", "at": "2026-09-05T00:00:00Z"}))
        self.assertTrue(is_authorized(self.ws))
        check_dispatch(Route("gemini", "x", "cheap", "http"), self.ws, confidential=True)

    def test_paused_shape(self):
        self.assertEqual(paused("quota")["status"], "paused")

if __name__ == "__main__":
    unittest.main()
