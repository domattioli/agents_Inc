"""Governance gateway: validate, authorize, reserve, invoke, audit in one pass."""
from __future__ import annotations
import os, uuid, hashlib, json, logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

from workerbees.envelope import Envelope, Decision, validate, canonical_hash
from workerbees.registry import Registry, RegistryError
from workerbees.policy import evaluate, PolicyError
from workerbees.control import Control, ControlError
from workerbees.ledger import record_dispatch, record_return
from workerbees.router import Route
from workerbees.adapters import base, claude, codex

logger = logging.getLogger(__name__)


class GatewayError(Exception):
    """Gateway initialization or configuration error."""
    pass


@dataclass
class GatewayResult:
    status: str  # allowed|denied|blocked|duplicate|conflict|envelope_invalid
    decision: Optional[Decision]
    worker_result: Optional[base.WorkerResult]
    node_id: str
    decision_recorded: bool


class Gateway:
    """Dispatch requests through governance checks with audit trail."""

    def __init__(self, workspace: Path, registry: Optional[Registry] = None,
                 control: Optional[Control] = None, mode: Optional[str] = None):
        self.workspace = Path(workspace).resolve()
        self.mode = mode or os.environ.get("WORKERBEES_GOVERNANCE", "off")

        if self.mode not in ("off", "shadow", "enforce"):
            raise GatewayError(f"Invalid WORKERBEES_GOVERNANCE mode: {self.mode}")

        self.registry = registry
        self.control = control or Control(self.workspace)

        if self.mode == "enforce" and not self.registry:
            raise GatewayError("enforce mode requires registry")

    def dispatch(self, envelope: Envelope, *, context: Dict[str, Any],
                 runner=base.run_worker, route: Route) -> GatewayResult:
        """Validate → authorize → reserve → invoke → audit. Never raises."""
        node_id = str(uuid.uuid4())
        run_id = context.get("run_id", str(uuid.uuid4()))

        # Step 1: Sender check
        auth_sender = context.get("authenticated_sender")
        if auth_sender is not None and auth_sender != envelope.sender:
            decision = Decision(False, node_id, "SENDER_MISMATCH", "Authenticated sender != envelope sender", "1.0", [])
            return GatewayResult(status="denied", decision=decision, worker_result=None, node_id=node_id, decision_recorded=False)

        # Step 2: Validate envelope
        errors = validate(envelope, {})
        if errors:
            return GatewayResult(status="envelope_invalid", decision=Decision(False, node_id, "ENVELOPE_INVALID", errors[0], "1.0", []), worker_result=None, node_id=node_id, decision_recorded=False)

        envelope_hash = canonical_hash(envelope)

        # Step 3: Replay check
        if self.mode in ("shadow", "enforce"):
            try:
                replay_result = self.control.check_replay(envelope.message_id, envelope_hash)
                if replay_result.state == "duplicate":
                    return GatewayResult(status="duplicate", decision=Decision(True, node_id, "DUPLICATE", "Same message ID and hash", "1.0", []), worker_result=None, node_id=node_id, decision_recorded=False)
                elif replay_result.state == "conflict":
                    decision = Decision(False, node_id, "REPLAY_CONFLICT", f"Message ID exists with different hash: {replay_result.reason}", "1.0", ["replay_check"])
                    if self.mode == "enforce":
                        self.control.record_decision(decision, run_id, node_id, envelope_hash)
                    return GatewayResult(status="conflict", decision=decision, worker_result=None, node_id=node_id, decision_recorded=self.mode == "enforce")
            except ControlError:
                if self.mode == "enforce":
                    return GatewayResult(status="blocked", decision=Decision(False, node_id, "AUDIT_UNAVAILABLE", "Control layer unavailable", "1.0", []), worker_result=None, node_id=node_id, decision_recorded=False)

        # Step 4: Policy evaluation
        decision = None
        if self.mode in ("shadow", "enforce"):
            if not self.registry:
                decision = Decision(False, node_id, "NO_REGISTRY", "Registry required", "1.0", [])
            else:
                decision = evaluate(context, envelope, self.registry)
        else:
            decision = Decision(True, node_id, "ALLOWED", "Off mode", "1.0", [])

        if decision and not decision.decision_id:
            decision.decision_id = str(uuid.uuid4())

        # Step 5: Record decision
        decision_recorded = False
        if self.mode in ("shadow", "enforce"):
            try:
                decision_recorded = self.control.record_decision(decision, run_id, node_id, envelope_hash)
                if self.mode == "enforce" and not decision_recorded:
                    return GatewayResult(status="blocked", decision=decision, worker_result=None, node_id=node_id, decision_recorded=False)
            except ControlError:
                if self.mode == "enforce":
                    return GatewayResult(status="blocked", decision=decision, worker_result=None, node_id=node_id, decision_recorded=False)

        # Step 6: Authorization check
        if not decision.allowed:
            if self.mode == "enforce":
                return GatewayResult(status="denied", decision=decision, worker_result=None, node_id=node_id, decision_recorded=decision_recorded)

        # Step 7: Provider registry check
        if self.registry and route:
            prov = self.registry.provider_for(envelope.recipient)
            if prov is not None and prov != route.provider:
                decision = Decision(False, node_id, "ROUTE_PROVIDER_MISMATCH", f"Provider mismatch: registry {prov} vs route {route.provider}", "1.0", decision.checked_rules if decision else [])
                if self.mode == "enforce" and not decision_recorded:
                    self.control.record_decision(decision, run_id, node_id, envelope_hash)
                return GatewayResult(status="denied", decision=decision, worker_result=None, node_id=node_id, decision_recorded=decision_recorded or (self.mode == "enforce"))

        # Step 8: Provider validation
        if route.provider not in ("claude", "codex"):
            decision = Decision(False, node_id, "PROVIDER_NOT_EXECUTABLE", f"Provider {route.provider} not executable", "1.0", decision.checked_rules if decision else [])
            if self.mode == "enforce" and not decision_recorded:
                self.control.record_decision(decision, run_id, node_id, envelope_hash)
            return GatewayResult(status="denied", decision=decision, worker_result=None, node_id=node_id, decision_recorded=decision_recorded or (self.mode == "enforce"))

        # Step 9: Check cancellation before reserve
        if self.mode in ("shadow", "enforce"):
            try:
                if self.control.is_cancelled(run_id):
                    return GatewayResult(status="cancelled", decision=decision, worker_result=None, node_id=node_id, decision_recorded=decision_recorded)
            except ControlError:
                pass

        # Step 10: Reserve budget
        if self.mode in ("shadow", "enforce"):
            try:
                reserved = self.control.reserve(run_id, node_id, calls=1, seconds=0.0)
                if not reserved and self.mode == "enforce":
                    return GatewayResult(status="blocked", decision=decision, worker_result=None, node_id=node_id, decision_recorded=decision_recorded)
            except ControlError:
                if self.mode == "enforce":
                    return GatewayResult(status="blocked", decision=decision, worker_result=None, node_id=node_id, decision_recorded=decision_recorded)

        # Step 11: Check cancellation before invoke
        if self.mode in ("shadow", "enforce"):
            try:
                if self.control.is_cancelled(run_id):
                    try:
                        self.control.release(run_id, node_id)
                    except ControlError:
                        pass
                    return GatewayResult(status="cancelled", decision=decision, worker_result=None, node_id=node_id, decision_recorded=decision_recorded)
            except ControlError:
                pass

        # Step 12: Check deadline
        timeout_arg = None
        if envelope.deadline:
            try:
                deadline_dt = datetime.fromisoformat(envelope.deadline.replace('Z', '+00:00')).replace(tzinfo=None)
                now_dt = context.get("now")
                if now_dt:
                    rem = (deadline_dt - now_dt).total_seconds()
                    if rem <= 0:
                        if self.mode in ("shadow", "enforce"):
                            try:
                                self.control.release(run_id, node_id)
                            except ControlError:
                                pass
                        expired_decision = Decision(False, node_id, "EXPIRED", "Envelope deadline expired", "1.0", decision.checked_rules if decision else [])
                        return GatewayResult(status="denied", decision=expired_decision, worker_result=None, node_id=node_id, decision_recorded=decision_recorded)
                    max_sec = envelope.budget.get("max_seconds", 300) if envelope.budget else 300
                    timeout_arg = int(min(rem, max_sec))
            except Exception:
                pass

        # Step 13: Record dispatch to ledger
        try:
            record_dispatch(self.workspace, node_id=node_id, run_id=run_id, model=route.model, tier=route.tier, task=envelope.intent, provider=route.provider, parent_id=context.get("parent_id"), edge_type=context.get("edge_type"))
        except Exception:
            pass

        # Step 14: Invoke worker
        try:
            if route.provider == "claude":
                cmd = claude.build_cmd(route.model)
            elif route.provider == "codex":
                cmd = codex.build_cmd(route.model, context.get("cwd"))
            else:
                raise ValueError(f"Unknown provider: {route.provider}")

            if timeout_arg is not None:
                worker_result = runner(cmd, envelope.payload.get("prompt", ""), cwd=context.get("cwd"), timeout=timeout_arg)
            else:
                worker_result = runner(cmd, envelope.payload.get("prompt", ""), cwd=context.get("cwd"))
        except Exception as e:
            worker_result = base.WorkerResult("failed", "", str(e), 1)
        finally:
            if self.mode in ("shadow", "enforce"):
                try:
                    self.control.release(run_id, node_id)
                except ControlError:
                    pass

        # Step 15: Record return to ledger
        try:
            record_return(self.workspace, node_id=node_id, status=worker_result.status, seconds=0.0, subscription_calls=1)
        except Exception:
            pass

        # Step 16: Store artifact only if output non-empty
        if worker_result.status in ("returned", "paused") and worker_result.output:
            output_hash = hashlib.sha256(worker_result.output.encode("utf-8")).hexdigest()
            try:
                self.control.store_artifact(envelope.message_id, envelope_hash, output_hash)
            except ControlError:
                pass

        return GatewayResult(status="allowed", decision=decision, worker_result=worker_result, node_id=node_id, decision_recorded=decision_recorded)
