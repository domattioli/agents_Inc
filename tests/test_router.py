import unittest
from workerbees.router import pick_model, pick_model_chain, Route, _TABLE

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

    def test_catalog_excludes_unavailable_mistral(self):
        self.assertIsNone(pick_model("extract", "cheap", {"mistral"}, True))

    def test_openrouter_named_chain_with_auto_last(self):
        chain = pick_model_chain("extract", "cheap", {"openrouter"}, True)
        self.assertGreater(len(chain), 2)
        self.assertNotEqual(chain[0].model, "openrouter/auto:free")
        self.assertEqual(chain[-1].model, "openrouter/auto:free")
        self.assertEqual(len({r.model for r in chain}), len(chain))
        self.assertTrue(all(r.provider == "openrouter" for r in chain))

    def test_mid_codex_default_then_quota_fallback(self):
        chain = pick_model_chain("review", "mid", {"codex"}, False)
        self.assertEqual([r.model for r in chain], ["gpt-5.6-luna", "gpt-5.6-sol"])

    def test_routing_top_level_keys_unchanged(self):
        self.assertEqual(sorted(_TABLE), ["optional", "optional_allowed_tasks",
            "optional_provider_wrappers", "required", "task_tier", "tiers"])

if __name__ == "__main__":
    unittest.main()
