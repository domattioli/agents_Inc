"""Governance checks run BEFORE any dispatch. Spend cap is structural: no paid path exists."""
from __future__ import annotations
import json, uuid
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from .router import Route, _TABLE
from .envelope import Envelope, Decision
from .registry import Registry, CLEARANCE_LEVELS

class PolicyError(Exception):
    """Dispatch refused by policy. Message is user-facing."""

def is_authorized(workspace: Path) -> bool:
    f = workspace / ".workerbees" / "authorization.json"
    if not f.exists():
        return False
    try:
        return bool(json.loads(f.read_text()).get("optional_providers"))
    except (json.JSONDecodeError, OSError):
        return False

def check_dispatch(route: Route, workspace: Path, confidential: bool) -> None:
    if route.provider in _TABLE["optional"] and confidential and not is_authorized(workspace):
        raise PolicyError(
            f"WB_WORKSPACE_AUTH_REQUIRED: {route.provider} may not receive confidential input; "
            f"grant per-workspace authorization in {workspace}/.workerbees/authorization.json")

def paused(reason: str) -> dict:
    return {"status": "paused", "reason": reason,
            "message": "Quota exhausted. Job paused; no paid fallback exists. Retry later."}

def evaluate(context: Dict[str, Any], envelope: Envelope, registry: Registry) -> Decision:
    """Pure policy evaluation: auth → parties → edge → operation → schema → classification → depth → expiry/cancel → approval → budget."""
    checked_rules, decision_id = [], uuid.uuid4().hex
    policy_version = registry.policy_version

    def deny(code: str, reason: str) -> Decision:
        return Decision(False, decision_id, code, reason, policy_version, checked_rules)

    try:
        # Auth: sender identity
        checked_rules.append("authenticated_sender")
        auth_sender = context.get("authenticated_sender")
        if not auth_sender:
            return deny("UNAUTHENTICATED_SENDER", "No authenticated sender")
        checked_rules.append("sender_mismatch")
        if auth_sender != envelope.sender:
            return deny("SENDER_MISMATCH", f"Auth sender '{auth_sender}' != envelope '{envelope.sender}'")

        # Parties: known sender & recipient
        checked_rules.append("known_sender")
        sender_agent = registry.agent(envelope.sender, include_disabled=True)
        if not sender_agent:
            return deny("UNKNOWN_SENDER", f"Sender '{envelope.sender}' not in registry")
        checked_rules.append("known_recipient")
        recipient_agent = registry.agent(envelope.recipient, include_disabled=True)
        if not recipient_agent:
            return deny("UNKNOWN_RECIPIENT", f"Recipient '{envelope.recipient}' not in registry")
        checked_rules.append("sender_enabled")
        if not sender_agent.enabled:
            return deny("SENDER_DISABLED", f"Sender '{envelope.sender}' disabled")
        checked_rules.append("recipient_enabled")
        if not recipient_agent.enabled:
            return deny("RECIPIENT_DISABLED", f"Recipient '{envelope.recipient}' disabled")

        # Edge: authorized relationship (D1: check BEFORE operation/schema)
        checked_rules.append("edge_exists")
        rel_type = "delegates_to" if envelope.operation == "request" else "requests"
        edge = registry.edge(envelope.sender, envelope.recipient, rel_type)
        if not edge:
            return deny("NO_EDGE", f"No '{rel_type}' from {envelope.sender} to {envelope.recipient}")

        checked_rules.append("intent_capability")
        intent = envelope.intent.removesuffix("ion") if envelope.intent == "extraction" else envelope.intent
        matching = [c for c in recipient_agent.capabilities
                    if c == intent or c.startswith(intent + ".")]
        if registry.capabilities and not matching:
            return deny("CAPABILITY_NOT_ALLOWED", f"Recipient lacks capability for '{envelope.intent}'")
        if any(not registry.capability(c, include_disabled=True).enabled for c in matching
               if registry.capability(c, include_disabled=True)):
            return deny("CAPABILITY_DISABLED", f"Capability for '{envelope.intent}' disabled")

        # Operation & schema validation
        checked_rules.append("operation_allowed")
        if envelope.operation not in {"request", "response", "error", "cancellation", "approval"}:
            return deny("OPERATION_NOT_ALLOWED", f"Operation '{envelope.operation}' not allowed")
        checked_rules.append("schema_allowed")
        if envelope.schema not in {"request_v1", "response_v1", "error_v1", "cancellation_v1", "approval_v1"}:
            return deny("SCHEMA_NOT_ALLOWED", f"Schema '{envelope.schema}' not allowed")

        # D3: Fail closed on unknown/None clearance
        checked_rules.append("classification_clearance")
        if sender_agent.clearance not in CLEARANCE_LEVELS or recipient_agent.clearance not in CLEARANCE_LEVELS:
            return deny("UNKNOWN_CLASSIFICATION", "Unknown sender or recipient clearance level")
        if envelope.data_classification not in CLEARANCE_LEVELS:
            return deny("UNKNOWN_CLASSIFICATION", f"Unknown classification '{envelope.data_classification}'")

        # D2: Check BOTH sender and recipient clearance >= data_classification
        sender_level = CLEARANCE_LEVELS.get(sender_agent.clearance, -1)
        rcv_level = CLEARANCE_LEVELS.get(recipient_agent.clearance, -1)
        env_level = CLEARANCE_LEVELS.get(envelope.data_classification, -1)
        if sender_level < env_level:
            return deny("CLASSIFICATION_EXCEEDED", f"Sender clearance '{sender_agent.clearance}' insufficient for '{envelope.data_classification}'")
        if rcv_level < env_level:
            return deny("CLASSIFICATION_EXCEEDED", f"Recipient clearance '{recipient_agent.clearance}' insufficient for '{envelope.data_classification}'")

        # D4: Delegation depth limit
        checked_rules.append("delegation_depth")
        edge_depth = edge.max_delegation_depth if edge.max_delegation_depth is not None else 1
        sender_depth = sender_agent.max_delegation_depth if sender_agent.max_delegation_depth is not None else 1
        depth_limit = min(edge_depth, sender_depth, 1)
        if context.get("depth", 0) > depth_limit:
            return deny("DELEGATION_DEPTH_EXCEEDED", f"Depth {context.get('depth')} exceeds limit {depth_limit}")

        # Expiry & cancellation
        checked_rules.append("not_expired")
        if envelope.expires_at:
            try:
                raw_now = context.get("now") or datetime.now(timezone.utc)
                now = raw_now if isinstance(raw_now, datetime) else datetime.fromisoformat(raw_now.replace("Z", "+00:00"))
                if now.tzinfo is None:
                    now = now.replace(tzinfo=timezone.utc)
                expires = datetime.fromisoformat(envelope.expires_at.replace("Z", "+00:00"))
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if now > expires:
                    return deny("EXPIRED", "Envelope expired")
            except (ValueError, AttributeError, TypeError):
                return deny("INVALID_EXPIRY", "Envelope expiry or clock is invalid")
        checked_rules.append("not_cancelled")
        if context.get("cancelled", False):
            return deny("CANCELLED", "Request cancelled")

        # D5: Approval required if registry edge OR capability OR envelope security says so
        checked_rules.append("approval_required")
        needs_approval = edge.requires_approval or envelope.security.get("approval_required", False)
        if needs_approval and not context.get("approval_valid", False):
            return deny("APPROVAL_REQUIRED", "Durable bound approval required by policy")

        # Budget: cost zero, usage within limits
        checked_rules.append("cost_zero")
        max_cost = envelope.budget.get("max_cost")
        if max_cost is not None and float(max_cost) > 0:
            return deny("COST_NOT_ZERO", f"max_cost must be 0, got {max_cost}")

        # D6: Budget check with projected usage
        checked_rules.append("budget_within_limits")
        budget_used = context.get("budget_used", {})
        calls, seconds = budget_used.get("calls", 0), budget_used.get("seconds", 0.0)
        max_calls = envelope.budget.get("max_calls", context.get("budget_limits", {}).get("max_calls"))
        max_seconds = envelope.budget.get("max_seconds", context.get("budget_limits", {}).get("max_seconds"))
        if envelope.budget.get("max_tokens") is not None:
            return deny("TOKEN_BUDGET_UNSUPPORTED", "Token caps are not enforceable by this gateway")
        projected_calls = calls + 1
        projected_seconds = seconds + (envelope.budget.get("max_seconds") or 0)
        if max_calls is not None and projected_calls > max_calls:
            return deny("BUDGET_EXCEEDED", f"Projected calls {projected_calls} > {max_calls}")
        if max_seconds is not None and projected_seconds > max_seconds:
            return deny("BUDGET_EXCEEDED", f"Projected seconds {projected_seconds} > {max_seconds}")

        # All rules passed
        return Decision(True, decision_id, "ALLOWED", "All policy rules satisfied", policy_version, checked_rules)
    except Exception as e:
        # D7: Wrap entire rule chain in try/except
        return deny("POLICY_ERROR", str(e)[:200])
