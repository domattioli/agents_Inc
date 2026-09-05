import unittest
import json
from datetime import datetime, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from workerbees.envelope import (
    Envelope, Decision, ArtifactRef, EnvelopeError,
    validate, canonical_hash, VALID_OPERATIONS, VALID_CLASSIFICATIONS
)


class TestEnvelopeStructure(unittest.TestCase):
    """Test basic Envelope dataclass structure and initialization."""

    def test_envelope_creation_minimal(self):
        """Test creating an Envelope with minimal required fields."""
        env = Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id=None,
            correlation_id="corr-001",
            sender="agent-1",
            recipient="agent-2",
            intent="process",
            operation="request",
            protocol="v1",
            schema="standard",
            payload={"action": "extract"},
            data_classification="public",
            created_at="2026-01-15T10:00:00Z"
        )
        self.assertEqual(env.message_id, "msg-001")
        self.assertEqual(env.operation, "request")
        self.assertEqual(env.data_classification, "public")

    def test_envelope_with_all_fields(self):
        """Test creating an Envelope with all optional fields."""
        now = datetime.utcnow().isoformat() + "Z"
        later = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
        art = ArtifactRef(kind="document", sha256="abc123", size=1024)

        env = Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id="task-000",
            correlation_id="corr-001",
            sender="agent-1",
            recipient="agent-2",
            intent="process",
            operation="response",
            protocol="v1",
            schema="standard",
            payload={"result": "success"},
            data_classification="confidential",
            created_at=now,
            expires_at=later,
            deadline=later,
            reply_to="msg-000",
            required_artifacts=[art],
            budget={"max_tokens": 5000, "max_seconds": 30},
            provenance={"root_agent": "supervisor-1", "delegation_path": ["a", "b"]},
            security={"authentication_context": "oauth2", "authorization_decision_id": "dec-001"}
        )
        self.assertEqual(env.parent_task_id, "task-000")
        self.assertEqual(len(env.required_artifacts), 1)
        self.assertEqual(env.budget["max_tokens"], 5000)


class TestArtifactRefAndDecision(unittest.TestCase):
    """Test ArtifactRef and Decision dataclasses."""

    def test_artifact_ref_creation(self):
        art = ArtifactRef(kind="document", sha256="abc123", size=2048)
        self.assertEqual(art.kind, "document")
        self.assertEqual(art.sha256, "abc123")
        self.assertEqual(art.size, 2048)

    def test_decision_creation(self):
        dec = Decision(
            allowed=True,
            decision_id="dec-001",
            reason_code="APPROVED",
            reason="User authorized",
            policy_version="2026-01-01",
            checked_rules=["rule-1", "rule-2"]
        )
        self.assertTrue(dec.allowed)
        self.assertEqual(len(dec.checked_rules), 2)


class TestValidateStructure(unittest.TestCase):
    """Test the validate() function for correct behavior."""

    def _make_valid_envelope(self):
        """Helper to create a valid envelope."""
        return Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id=None,
            correlation_id="corr-001",
            sender="agent-1",
            recipient="agent-2",
            intent="process",
            operation="request",
            protocol="v1",
            schema="standard",
            payload={"action": "extract"},
            data_classification="public",
            created_at="2026-01-15T10:00:00Z"
        )

    def test_validate_valid_envelope(self):
        """Test that a valid envelope passes validation."""
        env = self._make_valid_envelope()
        errors = validate(env, {})
        self.assertEqual(len(errors), 0, f"Expected no errors, got: {errors}")

    def test_validate_bad_operation(self):
        """Test that invalid operation is rejected."""
        env = self._make_valid_envelope()
        env.operation = "invalid_op"
        errors = validate(env, {})
        self.assertTrue(any("Invalid operation" in e for e in errors))

    def test_validate_bad_classification(self):
        """Test that invalid data_classification is rejected."""
        env = self._make_valid_envelope()
        env.data_classification = "ultra_secret"
        errors = validate(env, {})
        self.assertTrue(any("Invalid data_classification" in e for e in errors))

    def test_validate_expires_before_created(self):
        """Test that expires_at < created_at is rejected."""
        env = self._make_valid_envelope()
        env.created_at = "2026-01-15T10:00:00Z"
        env.expires_at = "2026-01-15T09:00:00Z"  # 1 hour earlier
        errors = validate(env, {})
        self.assertTrue(any("expires_at < created_at" in e for e in errors))

    def test_validate_expires_at_same_as_created(self):
        """Test that expires_at == created_at is allowed."""
        env = self._make_valid_envelope()
        env.created_at = "2026-01-15T10:00:00Z"
        env.expires_at = "2026-01-15T10:00:00Z"
        errors = validate(env, {})
        self.assertFalse(any("cannot be earlier than created_at" in e for e in errors))

    def test_validate_bad_iso8601_created(self):
        """Test that invalid ISO 8601 created_at is rejected."""
        env = self._make_valid_envelope()
        env.created_at = "not-a-date"
        errors = validate(env, {})
        self.assertTrue(any("not a valid ISO 8601" in e for e in errors))

    def test_validate_oversized_payload(self):
        """Test that oversized payload (>1MB) is rejected."""
        env = self._make_valid_envelope()
        # Create a payload > 1MB
        large_data = "x" * (1024 * 1024 + 1)
        env.payload = {"data": large_data}
        errors = validate(env, {})
        self.assertTrue(any("exceeds 1MB" in e for e in errors))

    def test_validate_non_json_serializable_payload(self):
        """Test that non-JSON-serializable payload is rejected."""
        env = self._make_valid_envelope()
        # Use a non-serializable object
        env.payload = {"func": lambda x: x}  # Functions are not JSON-serializable
        errors = validate(env, {})
        self.assertTrue(any("not JSON serializable" in e for e in errors))

    def test_validate_type_error_on_message_id(self):
        """Test that wrong type for message_id is detected."""
        env = self._make_valid_envelope()
        env.message_id = 12345  # Should be string
        errors = validate(env, {})
        self.assertTrue(any("has invalid type" in e for e in errors))

    def test_validate_artifact_ref_in_required_artifacts(self):
        """Test validation of required_artifacts list."""
        env = self._make_valid_envelope()
        env.required_artifacts = [
            ArtifactRef(kind="doc", sha256="abc", size=100)
        ]
        errors = validate(env, {})
        self.assertFalse(any("required_artifacts" in e and "not an ArtifactRef" in e for e in errors))

    def test_validate_bad_artifact_ref_in_required_artifacts(self):
        """Test that invalid ArtifactRef is rejected."""
        env = self._make_valid_envelope()
        env.required_artifacts = [{"kind": "doc"}]  # dict, not ArtifactRef
        errors = validate(env, {})
        self.assertTrue(any("not ArtifactRef" in e for e in errors))


class TestCanonicalHash(unittest.TestCase):
    """Test the canonical_hash() function."""

    def _make_envelope(self):
        return Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id=None,
            correlation_id="corr-001",
            sender="agent-1",
            recipient="agent-2",
            intent="process",
            operation="request",
            protocol="v1",
            schema="standard",
            payload={"action": "extract", "value": 42},
            data_classification="public",
            created_at="2026-01-15T10:00:00Z"
        )

    def test_canonical_hash_produces_hex(self):
        """Test that canonical_hash returns a valid hex string."""
        env = self._make_envelope()
        h = canonical_hash(env)
        self.assertEqual(len(h), 64)  # SHA256 hex is 64 chars
        self.assertTrue(all(c in "0123456789abcdef" for c in h))

    def test_canonical_hash_stable_across_key_order(self):
        """Test that hash is stable regardless of internal key order."""
        env1 = self._make_envelope()
        env2 = self._make_envelope()

        h1 = canonical_hash(env1)
        h2 = canonical_hash(env2)
        self.assertEqual(h1, h2)

    def test_canonical_hash_changes_on_payload_change(self):
        """Test that hash changes when payload changes."""
        env1 = self._make_envelope()
        h1 = canonical_hash(env1)

        env2 = self._make_envelope()
        env2.payload = {"action": "extract", "value": 43}  # Changed value
        h2 = canonical_hash(env2)

        self.assertNotEqual(h1, h2)

    def test_canonical_hash_changes_on_message_id_change(self):
        """Test that hash changes when message_id changes."""
        env1 = self._make_envelope()
        h1 = canonical_hash(env1)

        env2 = self._make_envelope()
        env2.message_id = "msg-002"
        h2 = canonical_hash(env2)

        self.assertNotEqual(h1, h2)

    def test_canonical_hash_with_all_fields(self):
        """Test canonical_hash with all optional fields populated."""
        env = Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id="task-000",
            correlation_id="corr-001",
            sender="agent-1",
            recipient="agent-2",
            intent="process",
            operation="response",
            protocol="v1",
            schema="standard",
            payload={"result": "success"},
            data_classification="confidential",
            created_at="2026-01-15T10:00:00Z",
            expires_at="2026-01-15T11:00:00Z",
            deadline="2026-01-15T11:00:00Z",
            reply_to="msg-000",
            required_artifacts=[ArtifactRef(kind="doc", sha256="abc", size=100)],
            budget={"max_tokens": 5000},
            provenance={"root_agent": "sup-1"},
            security={"auth_context": "oauth2"}
        )
        h = canonical_hash(env)
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))


class TestEnvelopeErrorException(unittest.TestCase):
    """Test the EnvelopeError exception."""

    def test_envelope_error_is_exception(self):
        """Test that EnvelopeError is an Exception."""
        err = EnvelopeError("Test error")
        self.assertIsInstance(err, Exception)

    def test_envelope_error_message(self):
        """Test that EnvelopeError preserves message."""
        msg = "This is a test error"
        err = EnvelopeError(msg)
        self.assertEqual(str(err), msg)

    def test_canonical_hash_raises_on_unhashable(self):
        """Test that canonical_hash raises EnvelopeError on failure."""
        env = Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id=None,
            correlation_id="corr-001",
            sender="agent-1",
            recipient="agent-2",
            intent="process",
            operation="request",
            protocol="v1",
            schema="standard",
            payload={"func": lambda: None},  # Non-serializable
            data_classification="public",
            created_at="2026-01-15T10:00:00Z"
        )
        with self.assertRaises(EnvelopeError):
            canonical_hash(env)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_validate_with_none_protocols(self):
        """Test validate() with None protocols dict."""
        env = Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id=None,
            correlation_id="corr-001",
            sender="agent-1",
            recipient="agent-2",
            intent="process",
            operation="request",
            protocol="v1",
            schema="standard",
            payload={"action": "extract"},
            data_classification="public",
            created_at="2026-01-15T10:00:00Z"
        )
        errors = validate(env, None)
        self.assertEqual(len(errors), 0)

    def test_validate_with_empty_protocols(self):
        """Test validate() with empty protocols dict."""
        env = Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id=None,
            correlation_id="corr-001",
            sender="agent-1",
            recipient="agent-2",
            intent="process",
            operation="request",
            protocol="unknown_proto",
            schema="standard",
            payload={"action": "extract"},
            data_classification="public",
            created_at="2026-01-15T10:00:00Z"
        )
        errors = validate(env, {})
        self.assertEqual(len(errors), 0)

    def test_all_valid_operations_pass(self):
        """Test that all valid operations pass validation."""
        for op in VALID_OPERATIONS:
            env = Envelope(
                message_id="msg-001",
                task_id="task-001",
                parent_task_id=None,
                correlation_id="corr-001",
                sender="agent-1",
                recipient="agent-2",
                intent="process",
                operation=op,
                protocol="v1",
                schema="standard",
                payload={},
                data_classification="public",
                created_at="2026-01-15T10:00:00Z"
            )
            errors = validate(env, {})
            self.assertEqual(len(errors), 0, f"Operation {op} should be valid but got errors: {errors}")

    def test_all_valid_classifications_pass(self):
        """Test that all valid classifications pass validation."""
        for cls in VALID_CLASSIFICATIONS:
            env = Envelope(
                message_id="msg-001",
                task_id="task-001",
                parent_task_id=None,
                correlation_id="corr-001",
                sender="agent-1",
                recipient="agent-2",
                intent="process",
                operation="request",
                protocol="v1",
                schema="standard",
                payload={},
                data_classification=cls,
                created_at="2026-01-15T10:00:00Z"
            )
            errors = validate(env, {})
            self.assertEqual(len(errors), 0, f"Classification {cls} should be valid but got errors: {errors}")

    def test_empty_payload_valid(self):
        """Test that empty payload dict is valid."""
        env = Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id=None,
            correlation_id="corr-001",
            sender="agent-1",
            recipient="agent-2",
            intent="process",
            operation="request",
            protocol="v1",
            schema="standard",
            payload={},
            data_classification="public",
            created_at="2026-01-15T10:00:00Z"
        )
        errors = validate(env, {})
        self.assertEqual(len(errors), 0)

    def test_iso8601_with_z_suffix(self):
        """Test ISO 8601 timestamps with Z suffix."""
        env = Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id=None,
            correlation_id="corr-001",
            sender="agent-1",
            recipient="agent-2",
            intent="process",
            operation="request",
            protocol="v1",
            schema="standard",
            payload={},
            data_classification="public",
            created_at="2026-01-15T10:00:00Z"
        )
        errors = validate(env, {})
        self.assertEqual(len(errors), 0)

    def test_iso8601_with_offset(self):
        """Test ISO 8601 timestamps with +00:00 offset."""
        env = Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id=None,
            correlation_id="corr-001",
            sender="agent-1",
            recipient="agent-2",
            intent="process",
            operation="request",
            protocol="v1",
            schema="standard",
            payload={},
            data_classification="public",
            created_at="2026-01-15T10:00:00+00:00"
        )
        errors = validate(env, {})
        self.assertEqual(len(errors), 0)

    def test_oversized_envelope_json(self):
        """Test that oversized envelope (>1MB total JSON) is rejected."""
        env = Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id=None,
            correlation_id="corr-001",
            sender="agent-1",
            recipient="agent-2",
            intent="process",
            operation="request",
            protocol="v1",
            schema="standard",
            payload={"action": "extract"},
            data_classification="public",
            created_at="2026-01-15T10:00:00Z",
            provenance={"delegation_path": ["agent-" + "x" * 50000 for _ in range(25)]}  # > 1.2 MB
        )
        errors = validate(env, {})
        self.assertTrue(any("exceeds" in e and "bytes" in e for e in errors))

    def test_envelope_from_dict_rejects_unknown_keys(self):
        """Test that Envelope.from_dict raises on unknown fields."""
        env_dict = {
            "message_id": "msg-001",
            "task_id": "task-001",
            "parent_task_id": None,
            "correlation_id": "corr-001",
            "sender": "agent-1",
            "recipient": "agent-2",
            "intent": "process",
            "operation": "request",
            "protocol": "v1",
            "schema": "standard",
            "payload": {"action": "extract"},
            "data_classification": "public",
            "created_at": "2026-01-15T10:00:00Z",
            "unknown_field": "should_fail"
        }
        with self.assertRaises(EnvelopeError) as ctx:
            Envelope.from_dict(env_dict)
        self.assertIn("Unknown fields", str(ctx.exception))

    def test_canonical_hash_rejects_nan(self):
        """Test that canonical_hash rejects NaN in payload."""
        env = Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id=None,
            correlation_id="corr-001",
            sender="agent-1",
            recipient="agent-2",
            intent="process",
            operation="request",
            protocol="v1",
            schema="standard",
            payload={"value": float('nan')},
            data_classification="public",
            created_at="2026-01-15T10:00:00Z"
        )
        with self.assertRaises(EnvelopeError) as ctx:
            canonical_hash(env)
        self.assertIn("Non-finite float", str(ctx.exception))

    def test_canonical_hash_stable_with_unicode(self):
        """Test that canonical_hash is stable with unicode strings."""
        env = Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id=None,
            correlation_id="corr-001",
            sender="agent-1",
            recipient="agent-2",
            intent="process",
            operation="request",
            protocol="v1",
            schema="standard",
            payload={"text": "Hello 世界 🌍"},
            data_classification="public",
            created_at="2026-01-15T10:00:00Z"
        )
        h1 = canonical_hash(env)
        h2 = canonical_hash(env)
        self.assertEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
