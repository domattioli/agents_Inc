"""workerbees/envelope.py - Envelope structures and validation for inter-agent messaging."""

from __future__ import annotations
import dataclasses
from dataclasses import dataclass, field
import datetime
import hashlib
import json
from typing import Any, Dict, List, Optional

class EnvelopeError(Exception):
    """Raised when an envelope operation or validation fails."""
    pass


@dataclass
class ArtifactRef:
    kind: str
    sha256: str
    size: int


@dataclass
class Decision:
    allowed: bool
    decision_id: str
    reason_code: str
    reason: str
    policy_version: str
    checked_rules: List[str] = field(default_factory=list)


@dataclass
class Envelope:
    message_id: str
    task_id: str
    parent_task_id: Optional[str]
    correlation_id: str
    sender: str
    recipient: str
    intent: str
    operation: str
    protocol: str
    schema: str
    payload: Dict[str, Any]
    data_classification: str
    created_at: str  # ISO 8601 string
    expires_at: Optional[str] = None
    deadline: Optional[str] = None
    reply_to: Optional[str] = None
    required_artifacts: List[ArtifactRef] = field(default_factory=list)
    budget: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    security: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Envelope":
        """Create Envelope from dict, raising EnvelopeError on unknown keys."""
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        unknown = set(d.keys()) - valid_fields
        if unknown:
            raise EnvelopeError(f"Unknown fields in Envelope: {sorted(unknown)}")
        return cls(**d)


VALID_OPERATIONS = {"request", "response", "error", "cancellation", "approval"}
VALID_CLASSIFICATIONS = {"public", "internal", "confidential", "restricted"}
MAX_PAYLOAD_SIZE_BYTES = 1024 * 1024
MAX_ENVELOPE_SIZE_BYTES = 1_000_000

def _is_iso8601(val: str) -> bool:
    if not isinstance(val, str):
        return False
    try:
        # Try parsing standard ISO format (with 'Z' or offset)
        cleaned = val.replace("Z", "+00:00")
        datetime.datetime.fromisoformat(cleaned)
        return True
    except (ValueError, TypeError):
        return False


def _validate_field_types(env: Envelope) -> List[str]:
    errors: List[str] = []

    type_checks = [
        ("message_id", env.message_id, str),
        ("task_id", env.task_id, str),
        ("parent_task_id", env.parent_task_id, (str, type(None))),
        ("correlation_id", env.correlation_id, str),
        ("sender", env.sender, str),
        ("recipient", env.recipient, str),
        ("intent", env.intent, str),
        ("operation", env.operation, str),
        ("protocol", env.protocol, str),
        ("schema", env.schema, str),
        ("payload", env.payload, dict),
        ("data_classification", env.data_classification, str),
        ("created_at", env.created_at, str),
        ("expires_at", env.expires_at, (str, type(None))),
        ("deadline", env.deadline, (str, type(None))),
        ("reply_to", env.reply_to, (str, type(None))),
        ("required_artifacts", env.required_artifacts, list),
        ("budget", env.budget, dict),
        ("provenance", env.provenance, dict),
        ("security", env.security, dict),
    ]

    for name, val, expected_type in type_checks:
        if not isinstance(val, expected_type):
            errors.append(f"Field '{name}' has invalid type: expected {expected_type}, got {type(val)}")

    return errors


def validate(envelope: Envelope, protocols: Dict[str, Any]) -> List[str]:
    """Validate Envelope: types, enums, protocol constraints, envelope/payload size, and chronology."""
    errors: List[str] = []
    if not isinstance(envelope, Envelope):
        return ["Envelope object is required."]
    type_errors = _validate_field_types(envelope)
    errors.extend(type_errors)
    if envelope.operation not in VALID_OPERATIONS:
        errors.append(f"Invalid operation '{envelope.operation}'. Must be one of {sorted(VALID_OPERATIONS)}.")
    if envelope.data_classification not in VALID_CLASSIFICATIONS:
        errors.append(f"Invalid data_classification '{envelope.data_classification}'.")
    if envelope.created_at and not _is_iso8601(envelope.created_at):
        errors.append(f"created_at is not a valid ISO 8601 string: '{envelope.created_at}'")
    if envelope.expires_at and not _is_iso8601(envelope.expires_at):
        errors.append(f"expires_at is not ISO 8601: '{envelope.expires_at}'")
    if envelope.deadline and not _is_iso8601(envelope.deadline):
        errors.append(f"deadline is not ISO 8601: '{envelope.deadline}'")
    if envelope.expires_at and envelope.created_at:
        try:
            c_dt = datetime.datetime.fromisoformat(envelope.created_at.replace("Z", "+00:00"))
            e_dt = datetime.datetime.fromisoformat(envelope.expires_at.replace("Z", "+00:00"))
            if e_dt < c_dt:
                errors.append("expires_at < created_at")
        except ValueError: pass
    try:
        payload_bytes = json.dumps(envelope.payload).encode("utf-8")
        if len(payload_bytes) > MAX_PAYLOAD_SIZE_BYTES:
            errors.append("Payload exceeds 1MB")
    except (TypeError, ValueError) as e:
        errors.append(f"Payload not JSON-serializable: {e}")
    try:
        env_dict = dataclasses.asdict(envelope)
        env_json = json.dumps(env_dict, sort_keys=True, separators=(",",":"), ensure_ascii=True)
        env_bytes = env_json.encode("utf-8")
        max_env_size = MAX_ENVELOPE_SIZE_BYTES
        if protocols and envelope.protocol in protocols:
            p_rules = protocols[envelope.protocol]
            if isinstance(p_rules, dict) and "envelope" in p_rules:
                max_env_size = p_rules["envelope"].get("maxBytes", MAX_ENVELOPE_SIZE_BYTES)
        if len(env_bytes) > max_env_size:
            errors.append(f"Envelope JSON exceeds {max_env_size} bytes")
    except (TypeError, ValueError) as e:
        errors.append(f"Envelope not JSON-serializable: {e}")
    for idx, art in enumerate(envelope.required_artifacts):
        if not isinstance(art, ArtifactRef):
            errors.append(f"required_artifacts[{idx}] not ArtifactRef")
    return errors


def canonical_hash(envelope: Envelope) -> str:
    """SHA256 of canonical JSON (sorted keys, no whitespace, ensure_ascii=True, no NaN)."""
    try:
        env_dict = dataclasses.asdict(envelope)
        canonical_json = json.dumps(
            env_dict, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    except (ValueError, TypeError) as e:
        if "Out of range float values" in str(e) or "NaN" in str(e):
            raise EnvelopeError(f"Non-finite float in envelope: {e}") from e
        raise EnvelopeError(f"Hash computation failed: {e}") from e
