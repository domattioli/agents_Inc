# CEO brief — graph-based agent governance / control plane (2026-09-05)

Verbatim operator objective. Source of truth for spec 003.

## Objective
Build a graph-based agent governance/control plane representing: agent identities/metadata; capabilities; relationships; allowed communication paths; delegation + escalation rules; tool/data-access permissions; message schemas/protocols; budgets, deadlines, retries, concurrency limits; human approval requirements; provenance, tracing, audit, policy decisions.

Core principle: the language model may propose a route or delegation, but deterministic runtime policy must approve or reject it. Never rely on prompts alone for security, permissions, topology, or communication rules.

## Target architecture
1. Agent graph registry — agents (stable id, name, version, owner, runtime/provider, endpoint, capabilities, IO schemas, protocols, trust level, data clearance, tool permissions, max delegation depth, max concurrency, budgets, health, auth, approval reqs) + first-class relationships (source, target, type ∈ {delegates_to, consults, submits_to, reviews, escalates_to, can_call, can_read, can_write, can_approve}, allowed operations/message types/tools, data limit, payload size, timeout, retry, budget, depth, recursive?, approval?, enabled, effective dates, reason/owner).
2. Capability registry — explicit machine-readable ids (e.g. research.summarize, code.write, deployment.approve) with schemas, risk level, permissions, data classification, approval?, delegable?, idempotent?, timeout/retry.
3. Policy decision layer — deterministic; answers registered sender? active recipient? edge exists? operation allowed? schema permitted? classification within clearance? depth exceeded? budget exceeded? approval required? tool permitted? expired/duplicate/cancelled? Returns structured decision {allowed, decision_id, reason_code, reason, policy_version, checked_rules}. Observable + auditable. Integrate OPA/Cedar/Casbin if present, else clean abstraction.
4. Communication protocol — typed versioned envelope: message_id, task_id, parent_task_id, correlation_id, sender, recipient, intent, operation, protocol, schema, payload, data_classification, created_at, expires_at, deadline, reply_to, required_artifacts, budget{max_tokens,max_seconds,max_cost}, provenance{root_agent, delegation_path}, security{authentication_context, authorization_decision_id}. Message kinds: request, response, event, progress, error, cancellation, approval request/response, escalation, retry, timeout. Runtime schema validation. A2A for agent↔agent if appropriate; MCP for tools; never conflate.
5. Runtime gateway/dispatcher — single enforcement boundary: authenticate, validate envelope, resolve parties, check edge, evaluate policy, budgets, payload schema, redaction, route, record decision, trace, enforce timeout/retry/cancel, validate response, record artifacts/provenance. No bypass.
6. Workflow vs governance graph — governance = who may talk to whom for what; workflow = what happens next. Workflow spawns only via approved edges; depth, parallelism, lineage, aggregation, review-before-complete, escalation, pause/resume for approval, cascade cancel.
7. Human approval — explicit for high-risk (prod write, deploy, delete, external comms, sensitive data, grant perms, approve another agent's result). Request carries agent, action, resource, artifacts, risk, rules triggered, expiry, approver, decision, timestamp. No self-approval.

## Structure (adapt, don't copy)
agent-system/{graph/{agents,capabilities,relationships}.yaml + schemas/, policies/*.rego, protocols/*.schema.json, runtime/{registry,policy,dispatcher,gateway,budgets,approvals}, workflows/, agents/, tests/{unit,integration,policy,protocol,end_to_end}}. Versioned config + schemas, reviewable in git.

## Security requirements
All agent output untrusted. Validate every message; authenticate identity; authorize every call; no arbitrary recipient/capability claims; least privilege; classification boundaries; max depth; rate/token/time/cost budgets; no recursive spawn loops; no prompt-based privilege escalation; record decisions; no secret leakage; secrets never in model context; tool perms narrower than agent perms; cancel/timeout propagation; idempotent retries; fail closed on unknown agent/capability/schema/missing decision.

## Observability
Structured logs/traces: registration, graph version, message/task/parent ids, sender, recipient, operation, capability, decision + policy version, budget usage, tool calls, approvals, errors, retries, timeouts, cancellation, outcome. No secrets/PII. Must reconstruct initiator, contacts, allow/deny reasons, data/tools used, policy version, artifact authorship, failure point.

## Example config (yaml)
agents: planner{task.decompose, worker.delegate; trust high; depth 2}, researcher{research.web_search, research.summarize; trust medium; clearance internal}, implementer{code.read/write/test; medium; confidential}, reviewer{code.review, test.review; high}.
relationships: planner→researcher delegates_to [research] schemas [ResearchRequest.v1] conc 4 timeout 180; planner→implementer delegates_to [implementation] conc 1; implementer→reviewer submits_to [review]; implementer→production can_write [deploy] enabled false requires_human_approval true.

## Phases
1 architecture+inventory · 2 domain model (Agent, Capability, Relationship, Resource, Policy, MessageEnvelope, Task, Artifact, ApprovalRequest, PolicyDecision) · 3 graph registry · 4 policy evaluation · 5 dispatcher/gateway · 6 workflow integration · 7 tests · 8 docs.

## Required tests
allowed delegation ok; unknown sender/recipient denied; missing edge denied; disallowed op/schema denied; classification enforced; depth enforced; token/time/cost budgets enforced; recursive spawn prevented; expired rejected; invalid payload rejected; high-risk needs approval; no self-approval; cancel propagates; retries idempotent; decisions auditable; provenance records chain; prompt cannot override perms; compromised worker cannot bypass gateway.

## Constraints
Small composable interfaces; provider-agnostic; declarative versioned config; deterministic enforcement; LLM never source of truth for authz; no graph DB unless needed (in-repo versioned graph + persistence abstraction); no premature distribution; backwards compat + adapters; feature flags; explainable denials.

## Deliverable order
Smallest complete vertical slice first: registry → graph edge → policy decision → typed message → dispatcher → one supervisor → one worker → one denied request → one successful request → audit/tracing for both. Then expand only where it fits.

## Operator constraints for THIS repo (added by CTO)
- caveman ultra for every agent prompt.
- Code written by free/cheapest models (gemini flash via gask.sh where non-confidential; else gpt-5.4-mini / haiku). Review by gpt-5.6-luna, sonnet fallback. No frontier at build time except astra for planning.
- Build starts after spec 002 (dispatch graph ledger) lands: the ledger is the provenance/audit substrate this plane consumes.
