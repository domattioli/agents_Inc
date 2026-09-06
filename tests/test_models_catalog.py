import unittest
import json
import re
from pathlib import Path

# Models that are non-text (e.g., music generation) and legitimately have ctx_hint == 0
NON_TEXT_MODELS = {"google/lyria-3-pro-preview", "google/lyria-3-clip-preview"}


class TestModelsCatalog(unittest.TestCase):
    """Validate models.json catalog structure and completeness."""

    @classmethod
    def setUpClass(cls):
        """Load models.json and routing.json once for all tests."""
        base_dir = Path(__file__).parent.parent
        models_path = base_dir / "workerbees" / "models.json"
        routing_path = base_dir / "workerbees" / "routing.json"
        doc_path = base_dir / "docs" / "free-openrouter-models.md"

        with open(models_path) as f:
            cls.models_data = json.load(f)
        with open(routing_path) as f:
            cls.routing_data = json.load(f)
        with open(doc_path) as f:
            cls.doc_text = f.read()

    def test_models_json_structure(self):
        """models.json parses; version nonempty str."""
        self.assertIsInstance(self.models_data, dict)
        self.assertIn("version", self.models_data)
        self.assertIsInstance(self.models_data["version"], str)
        self.assertGreater(len(self.models_data["version"]), 0)
        self.assertIn("models", self.models_data)
        self.assertIsInstance(self.models_data["models"], dict)

    def test_all_profiles_have_required_fields(self):
        """Every profile has all required fields with correct types."""
        required_fields = {
            "vendor": (str, type(None)),
            "provider": str,
            "tier": str,
            "tasks_good": list,
            "tasks_bad": list,
            "ctx_hint": int,
            "cost_class": str,
            "status": str,
        }
        for model_id, profile in self.models_data["models"].items():
            for field, expected_type in required_fields.items():
                self.assertIn(
                    field, profile, f"Model {model_id} missing field {field}"
                )
                if isinstance(expected_type, tuple):
                    self.assertIsInstance(
                        profile[field],
                        expected_type,
                        f"Model {model_id} field {field} has wrong type",
                    )
                else:
                    self.assertIsInstance(
                        profile[field],
                        expected_type,
                        f"Model {model_id} field {field} has wrong type",
                    )

    def test_cost_class_values(self):
        """cost_class must be one of allowed values."""
        allowed = {"free", "cheap", "mid", "premium"}
        for model_id, profile in self.models_data["models"].items():
            self.assertIn(
                profile["cost_class"],
                allowed,
                f"Model {model_id} has invalid cost_class",
            )

    def test_vendor_provider_invariant(self):
        """Broker pass-through routes must not claim a vendor."""
        for model_id, profile in self.models_data["models"].items():
            # Rule 1: If provider is openrouter AND model_id starts with openrouter/,
            # then vendor must be None
            if profile["provider"] == "openrouter" and model_id.startswith("openrouter/"):
                self.assertIsNone(
                    profile["vendor"],
                    f"Model {model_id} has provider=openrouter and model_id starts with "
                    f"'openrouter/' but vendor is not None (got {profile['vendor']})",
                )
            # Rule 2: No profile may have vendor == "openrouter"
            self.assertNotEqual(
                profile["vendor"],
                "openrouter",
                f"Model {model_id} has vendor='openrouter'; vendors must be model makers, "
                f"not broker aliases",
            )

    def test_status_values(self):
        """status must be one of allowed values."""
        allowed = {"available", "unprobed", "unavailable"}
        for model_id, profile in self.models_data["models"].items():
            self.assertIn(
                profile["status"],
                allowed,
                f"Model {model_id} has invalid status",
            )

    def test_tier_values(self):
        """tier must be one of allowed values."""
        allowed = {"cheap", "mid", "frontier"}
        for model_id, profile in self.models_data["models"].items():
            self.assertIn(
                profile["tier"],
                allowed,
                f"Model {model_id} has invalid tier",
            )

    def test_task_vocabulary(self):
        """Every task string in tasks_good/tasks_bad is from allowed vocabulary."""
        allowed_tasks = {
            "extract",
            "summarize",
            "draft",
            "review-draft",
            "review-of-record",
            "code-write",
            "code-review",
            "orchestrate",
            "classify",
        }
        for model_id, profile in self.models_data["models"].items():
            for task in profile["tasks_good"]:
                self.assertIn(
                    task,
                    allowed_tasks,
                    f"Model {model_id} has invalid task_good: {task}",
                )
            for task in profile["tasks_bad"]:
                self.assertIn(
                    task,
                    allowed_tasks,
                    f"Model {model_id} has invalid task_bad: {task}",
                )

    def test_routing_json_models_in_catalog(self):
        """EVERY model string in routing.json is present in models.json."""
        routing_models = set()

        # Extract all model strings from tiers
        for tier_name, providers in self.routing_data["tiers"].items():
            for provider, model_id in providers.items():
                routing_models.add(model_id)

        for model_id in routing_models:
            self.assertIn(
                model_id,
                self.models_data["models"],
                f"Model {model_id} from routing.json not in models.json",
            )

    def test_openrouter_models_in_catalog(self):
        """EVERY OpenRouter model id from doc is in models.json."""
        # Extract model IDs from doc headers
        # Format: ### N. <model_id>:free or ### N. <model_id>
        pattern = r"^### \d+\. ([a-z0-9/\-\.]+(?::free)?)"
        openrouter_models = []

        for match in re.finditer(pattern, self.doc_text, re.MULTILINE):
            model_id = match.group(1).strip()
            openrouter_models.append(model_id)

        # Expected 22 models in the doc
        self.assertGreaterEqual(
            len(openrouter_models),
            22,
            f"Found {len(openrouter_models)} models in doc, expected at least 22",
        )

        for model_id in openrouter_models:
            self.assertIn(
                model_id,
                self.models_data["models"],
                f"OpenRouter model {model_id} not in models.json",
            )

    def test_no_key_like_strings(self):
        """No value in models.json matches key-like regex."""
        key_pattern = re.compile(r"sk-[A-Za-z0-9]|[A-Za-z0-9+/=]{32,}")

        def check_value(value, path):
            if isinstance(value, str):
                if key_pattern.search(value):
                    self.fail(
                        f"Found key-like string at {path}: {value[:50]}"
                    )
            elif isinstance(value, dict):
                for k, v in value.items():
                    check_value(v, f"{path}.{k}")
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    check_value(v, f"{path}[{i}]")

        check_value(self.models_data, "models.json")

    def test_ctx_hint_bounds(self):
        """ctx_hint must be >= 1000 for text models; 0 only for non-text models in allowlist."""
        for model_id, profile in self.models_data["models"].items():
            ctx = profile["ctx_hint"]
            if model_id in NON_TEXT_MODELS:
                self.assertEqual(
                    ctx, 0,
                    f"Model {model_id} is in NON_TEXT_MODELS and must have ctx_hint == 0, got {ctx}"
                )
            else:
                self.assertGreaterEqual(
                    ctx, 1000,
                    f"Model {model_id} ctx_hint {ctx} must be >= 1000 for text models"
                )


if __name__ == "__main__":
    unittest.main()
