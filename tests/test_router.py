import unittest
from workerbees.router import pick_model, Route

class RouterTest(unittest.TestCase):
    def test_cheap_extract_prefers_required_provider(self):
        r = pick_model("extract", "cheap", {"claude", "codex"}, workspace_authorized=False)
        self.assertEqual((r.provider, r.model, r.tier), ("claude", "haiku", "cheap"))

    def test_optional_provider_denied_without_authorization(self):
        r = pick_model("extract", "cheap", {"gemini"}, workspace_authorized=False)
        self.assertIsNone(r)

    def test_optional_provider_allowed_with_authorization(self):
        r = pick_model("extract", "cheap", {"gemini"}, workspace_authorized=True)
        self.assertEqual(r.provider, "gemini")

    def test_review_uses_other_vendor(self):
        r = pick_model("review", "mid", {"claude", "codex"}, workspace_authorized=False, exclude_provider="claude")
        self.assertEqual(r.provider, "codex")

    def test_unknown_tier_none(self):
        self.assertIsNone(pick_model("extract", "platinum", {"claude"}, workspace_authorized=False))

    def test_prefer_provider(self):
        r = pick_model("extract", "cheap", {"claude", "codex"}, workspace_authorized=False, prefer_provider="codex")
        self.assertEqual(r.provider, "codex")
        self.assertEqual(r.model, "gpt-5.4-mini")

if __name__ == "__main__":
    unittest.main()
