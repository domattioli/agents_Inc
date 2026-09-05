# GOVERNANCE ASSESSMENT

## 1 CURRENT ARCH

Read-only snapshot: 2026-09-05. Ledger present; treated as available. No provider calls, tests, or repo writes made. Paths below relative to repo root; citations name actual symbols. CEO objective: `docs/governance/CEO-BRIEF.md`, read fully.

| Plane | Exists now | Boundary missing |
|---|---|---|
| Registry | `workerbees/router.py:Route`, `pick_model`; `workerbees/routing.json` lists providers, tiers, tasks, wrapper paths. | No stable agent identity, owner/version, clearance, capability registry, or authorized edges. Model ID ≠ agent ID. |
| Capability | `workerbees/adapters/claude.py:build_cmd`, `adapters/codex.py:build_cmd` suppress tools; `pipeline.py:_cmd` selects implementation. | No machine-checked operation/schema/tool contract. Optional routes exist without Python transports. |
| Policy | `workerbees/policy.py:check_dispatch`, `is_authorized`: D7 workspace grant. `router.py:pick_model`: eligibility, tier, provider exclusion. | No structured decision, authenticated sender, graph authorization, budget reservation, approval, or pre-dispatch depth check. |
| Envelope | `pipeline.py:BriefResult`, `reviewer.py:ReviewResult`, `adapters/base.py:WorkerResult`; JSON worker/reviewer prompts. | Result containers only. No versioned request, expiry, identity binding, replay control, cancellation, or frozen policy version. |
| Gateway | `pipeline.py:brief` routes worker/correction; `reviewer.py:review`, `doctor.py:probe_cli` invoke runners separately. | Three dispatch paths. Reviewer skips `check_dispatch`; supplied route bypasses provider exclusion. Doctor treats non-Claude as Codex. |
| Approval | `policy.py:is_authorized` reads `.workerbees/authorization.json`; `pipeline.py:brief` sets human-decision receipt. | Blanket optional-provider grant, not action approval. No approver identity, expiry, resource/artifact binding, or no-self-approval rule. |
| Acceptance | `verifier.py:verify`, `passed`, `check_draft`; `reviewer.py:review`; `pipeline.py:brief`. | Preserve these gates. Gateway permission never means verified output. |
| Audit | `ledger.py:record_dispatch`, `record_return`, `load`, `lint`, `rollup`, `to_json`, `to_mermaid`. | Invocation graph; no full allow/deny decisions, graph version, approval evidence, or artifact hash linkage. |
| Legacy execution | `skills/codex-bridge/scripts/agent_runner.py:submit`, `run_worker`, `save_job`, `write_artifact`. | Separate JSON jobs, wrappers, retries and status authority. `mark_verified` checks status, not verifier evidence. |

`route.sh:_get_chain` owns another routing table plus cooldowns. Legacy `routing-policy.md` describes tool-capable workers; current Workerbees contract says tool-free. Do not merge their authority by importing prose.

## 2 EXISTING ABSTRACTIONS TO REUSE vs GAPS

| Reuse | Keep | Add / correct |
|---|---|---|
| `router.pick_model` | Candidate ordering; required/optional split; model IDs stay in `routing.json`. | Intersect candidates with executable, authorized registry entries first; policy independently validates chosen route. `task_tier` is not used by this function. |
| `policy.check_dispatch` | Existing API and D7 error code. | Make it a compatibility guard beside structured `evaluate`; strict boolean grant parsing. Current truthiness accepts malformed nonempty values. |
| Ledger | Existing node IDs, run IDs, edges, exports, calls/seconds rollup. | Join decisions by node ID; denied requests create decisions, not phantom model calls. Ledger remains a projection, never the permission oracle. |
| Doctor | `run`, `available`, `probe_cli`; auth/quota diagnostics and cache. | Gateway issues synthetic probe grants without consulting doctor recursively. Bind health to model/CLI/config version; PONG alone proves no isolation. |
| “agent_runner SQLite” | Reuse ID/artifact concepts and execution ownership. | Premise false: `agent_runner.py` uses `job.json`. SQLite is `usage_db.py:init_db`, `ingest_delegated_usage`; telemetry only, not a scheduler or budget authority. |
| `data_policy.py` | Legacy `prepare_prompt` compatibility only. | Appends an opt-out declaration. No classification, provider grant, redaction, or technical enforcement. Never count it as D7 protection. |

Concrete ledger caveats: `ledger.py` is 358 lines, already above its plan's 300-line target; leave landed dependency untouched in this slice. `lint.compute_depth` lacks cycle detection; validate graph cycles before calling it on imported data. `pipeline.brief` attaches repeat review to original worker, not corrected artifact. Add explicit artifact/attempt linkage in decision metadata.

Spec drift: 002 plan says correction absent; code has it. Spec clarification promises eventual runner-ledger replacement; FR-009 preserves current authority. Treat replacement as later migration, not permission for dual writers now.

## 3 PROPOSED CHANGES

Smallest slice: trusted local supervisor → registered tool-free worker → valid candidate; forbidden operation → deterministic denial; both decisions inspectable. Then route reviewer, correction and doctor through same boundary.

Use JSON. No YAML parser; no OPA/Cedar/Casbin dependency present in inspected runtime. Validate a deliberately small schema vocabulary with stdlib; reject unsupported schema features. No HTTP, A2A, MCP server, graph database, or daemon needed for local calls.

Eight runtime module files maximum; proposed final caps below, all ≤300 lines, stdlib only. Config and tests separate from module count; keep each new config/test file ≤300 lines too.

| File under `workerbees/` | Cap | Owns |
|---|---:|---|
| `registry.py` new | 180 | Load versioned JSON; Agent, Capability, Relationship, Resource records; validate references, enabled/effective dates, immutable snapshot; map agent IDs to existing routes. |
| `envelope.py` new | 220 | Typed Envelope, Decision, Artifact references; strict field/type/size validation; canonical hashes; operation-specific request/response schemas. |
| `policy.py` extend | 240 | Pure `evaluate(context, envelope, registry)`; legacy `check_dispatch` retained; reason codes and checked-rule IDs; classification mapping; no I/O inside evaluation. |
| `control.py` new | 290 | Workspace SQLite transactions: decisions, reservations, replay keys, cancellation and approval records; run lease; audit joins to ledger IDs. No copy of provider execution status. |
| `gateway.py` new | 290 | Authenticate local context, validate, authorize, reserve, invoke registered adapter, validate response, emit ledger and decision events, release reservation in `finally`. |
| `pipeline.py` adapt | 280 | Keep extraction, correction and acceptance logic; remove inline dispatch/ledger boilerplate; call gateway with frozen run context. |
| `reviewer.py` adapt | 120 | Keep prompt and verdict validation; explicit reviewer capability; gateway invocation; enforce vendor difference even for supplied routes. |
| `doctor.py` adapt | 140 | Registered synthetic probe operation; gateway invocation; cache and diagnostics unchanged externally. |

Declarative assets: `workerbees/governance.json` holds graph, capabilities and policy defaults; `workerbees/protocols.json` holds bounded schemas. Existing `routing.json` remains sole model-name table. Snapshot hash covers all three. Caller/model cannot nominate another config file.

Seed graph: supervisor delegates extraction/correction, requests independent review, invokes doctor probes. Worker/reviewer have no outgoing spawn/tool edges. Deployment/delete/send/grant capabilities disabled. Unknown identities, capabilities, edges, schemas and message kinds denied.

Envelope v1: message/task/parent/correlation IDs; sender/recipient; intent/operation/protocol/schema; payload; classification; created/expiry/deadline; reply target; required artifacts; budget; root/delegation path; authentication context; decision reference. Gateway derives security fields from trusted context, ignores no caller override. Bind source, prompt, candidate and review hashes.

First supported kinds: request, response, error, cancellation, approval request/response. Progress/event/escalation/retry/timeout need explicit schemas before acceptance. No generic passthrough. Retry creates an attempt under one logical request; terminal duplicate returns stored artifact reference; changed payload under same ID denied.

Policy order: shape/authentication → registered parties/edge → operation/schema/tools → classification → lineage/expiry/cancel → approval → atomic budget/concurrency reservation. Decision: allowed, decision_id, reason_code, reason, policy_version, checked_rules. Record denials too; secret-free identifiers and hashes, never prompts or raw stderr.

Approval: persist pending action/resource/artifact hash, risk, rule IDs, expiry, approver, decision/time. Return blocked/pending without dispatch. Resume only after trusted human response, different identity from requester, bound to unchanged action; re-evaluate current policy. Approval cannot enable disabled deployment or waive D9.

Budget slice: $0 exact Decimal cap; subscription-call reservation; monotonic wall deadline; one active run/workspace, one model call at a time; one correction; at most one proven-transient retry. Probe calls charged separately but visibly. Quota pauses; no reroute around exhaustion.

Token limit truth: existing CLI adapters expose no proven hard total-token bound. Record unknown usage as null. Reject requests requiring finite token enforcement until transport proves a cap including hidden/reasoning tokens; never treat character estimates as enforcement. First successful slice uses explicit unsupported/null token budget, finite time/calls and hard $0.

Timeout/cancel: gateway-managed process group for production transport; bounded stdout/stderr capture, deadline polling, terminate then kill; cancellation persists and stops descendants before another call starts. Keep injectable fake runner for tests. No shell command strings; fixed adapter argv only.

Audit split: control transaction durably stores allow/deny before invocation; failure blocks strict dispatch. Existing graph append failure remains nonfatal with `ledger_error`, honoring 002 FR-008. Control audit supplies decision/provenance facts; ledger supplies invocation graph. Same IDs, no duplicate job-state machine.

Graph algorithms: adjacency lookup for permission; path membership/depth for recursion; cycle/topological checks only on delegation/dependency subgraphs. A review relation may point back without authorizing recursive spawn. Workflow sequencing remains in `brief`. Ledger edge direction is child → parent; do not confuse it with governance sender → recipient.

Tokenomics: first collect calls per accepted task, attempts, outcomes and elapsed time by task/provider/version. Compare only quality-qualified routes. Shortest-path optimization comes after measured edge weights and valid workflow alternatives; choosing a cheap communication path does not prove workflow quality. Sum of node seconds ≠ parallel wall time. Critical path useful once actual parallel dependencies exist; min-cost flow/bandits deferred.

## 4 RISKS — TOP 5

1. **Dual authority / bypass.** Legacy runner can invoke wrappers outside gateway and manually mark results verified. Keep strict Workerbees transport direct; never wrap one invocation in both runners. Legacy jobs remain explicitly ungoverned until an authenticated shim replaces dispatch. Same-UID arbitrary Python/shell can bypass library code: security claim covers tool-free worker processes, not a malicious host with owner privileges.
2. **D9 budgets, `/bin/zsh`, cost fields.** Shell availability grants neither money nor quota. `/bin/zsh` is a host execution detail, not an allowed worker capability; `route.sh`/`gask.sh` actually declare Bash. JSON `max_cost` cannot prevent a billable wrapper. Strict registry enables only proven subscription/free routes, rejects positive cost requests and unknown billing, pauses on quota. Calls, wall time, tokens and dollars remain distinct. Hard token caps currently unsupported.
3. **D7 classification mapping.** Map legacy confidential=true → confidential; false → public only as trusted caller attestation. Unknown defaults confidential; invalid labels rejected. Proposed order public < internal < confidential < restricted; internal conservatively needs optional-provider grant too; restricted disabled pending explicit resource authorization. Existing workspace grant permits optional-provider confidential egress only, not tool use, new capability or high-risk action. `data_policy.py` changes none of this.
4. **Audit failure / graph lies.** Best-effort ledger cannot authorize, reserve budget, or prove complete tracing. Cyclic imported parents can hang current lint; repeat review lacks corrected-artifact identity. Use cycle-safe prevalidation, decision transaction, artifact hashes and call-count reconciliation. Freeze reviewed file hashes after ledger writer settles; docs' 97-pass report is not a fresh test result.
5. **False confidence from identity/isolation/approval.** Model-declared sender, supplied reviewer route, cached PONG and approval booleans are insufficient. Host owns identity/context; registry binds actual vendor, not provider alias; strict tools disabled; approval exact-action-bound. Negative probes required. Existing verdict parser also assumes verdict entries are dicts: reject malformed response before semantic checks. Never promote on exit 0 or authorization alone.

## 5 MIGRATION

Feature flag: `WORKERBEES_GOVERNANCE=off|shadow|enforce`; default off during rollout. Trusted launcher owns mode; model payload cannot change it. Explicit unsupported value fails startup. Production enforce never falls back to off on error.

Off: preserve signatures, positional parameters, `runner=` seam, return types, status rules and existing ledger behavior. Add optional keyword-only gateway context to reviewer/probe helpers. Standalone helpers in enforce require workspace/context; absent context blocks rather than bypasses.

Shadow: evaluate and record proposed decisions; existing execution unchanged; no extra model calls. Synthetic/non-confidential fixtures only until strict path proven. Label audit as shadow, never as enforced authorization.

Enforce: `brief` freezes run/config/source identity; gateway routes each worker/correction. Reviewer independently enters gateway with original source and candidate hash. Doctor enters registered public synthetic probe path; gateway never calls `doctor.available`. Use supplied health snapshot for ordinary dispatch to avoid recursion.

Move model-call ledger emission into gateway only in enforce; remove duplicate outer hooks for that mode. Normal worker+reviewer stays two nodes/one review edge. Corrections retain 002 graph shape; artifact metadata identifies exact candidate reviewed. Doctor retains one root probe node/provider.

Compatibility gate: all original 75 tests plus every landed ledger test, flag off; repeat applicable behavior tests with enforce and injected transport. Local static scan found 101 test methods; DECISIONS reports 97 passes. Reconcile live collection after writer finishes; do not promise stale count. No tests executed for this investigation.

Preserve quota pause, retained draft after failed correction, reviewer independence, disabled-review result, source/citation checks, no false accepts. Add exact assertions: denial invokes runner zero times; every invocation one node; allow/deny both reconstructable; decision-store failure blocks while graph-write failure preserves outcome.

Cutover proof includes both entry hosts, Tim/Dom fixtures, direct review/probe calls, restart replay, changed-payload duplicate, deadline/cancel, stale approval, malformed messages and prompt-injection attempts. Disable legacy wrapper access from governed workers. Full host-wide no-bypass awaits legacy shim/isolation; do not market it early.

## 6 BUILD PLAN

Plan only; no build/delegation authorized or performed here. Start on stable spec-002 snapshot. Eight-file runtime slice above first; unsupported capabilities stay disabled. Each row: one bounded builder call + one reviewer call. No frontier during build or repair.

G = gemini-flash via `gask.sh`, only explicitly non-confidential bounded input; H = haiku; M = gpt-5.4-mini. L = gpt-5.6-luna; S = sonnet fallback. If G lacks disclosure/free-route clearance, use H or M. M + L is same-vendor build review; use S where independent-vendor review is required. Runtime document review always other-vendor.

| Phase | Task | BUILDER | REVIEWER | Est. calls |
|---|---|---|---|---:|
| Contract | 1 Freeze 002 hashes; inventory call sites; spec-003 scope and unsupported-capability denials. | H | L → S | 2 |
| Contract | 2 JSON graph/capabilities/schema fixtures; allow and deny examples; version/hash rules. | G | L → S | 2 |
| Domain | 3 `registry.py`; duplicate IDs, invalid dates, missing refs, operation edges. | G | L → S | 2 |
| Domain | 4 `envelope.py`; strict scalar/container types, payload limits, canonical hashes. | G | L → S | 2 |
| Policy | 5 Extend `policy.py`; auth/edge/schema/tools/classification/depth/expiry decisions. | H | L → S | 2 |
| State | 6 `control.py`; atomic replay keys, decision log, reservations, run lease. | H | L → S | 2 |
| State | 7 Approval pending/resume, no self-approval, expiry and resource/hash binding. | H | L → S | 2 |
| Gateway | 8 `gateway.py`; registry-only adapter resolution, allow/deny audit, ledger linkage. | H | L → S | 2 |
| Gateway | 9 Deadline/process-group cancel, output bounds, retry/replay, exception cleanup. | H | L → S | 2 |
| Slice | 10 One supervisor/worker success + forbidden-operation denial; inspect both traces. | G | L → S | 2 |
| Integrate | 11 `pipeline.py`; worker/correction context, preserve acceptance and receipt contracts. | H | L → S | 2 |
| Integrate | 12 `reviewer.py`; explicit context, vendor enforcement, candidate/response validation. | H | L → S | 2 |
| Integrate | 13 `doctor.py`; probe capability, cache context, no bootstrap recursion. | H | L → S | 2 |
| Verify | 14 Flag matrix; original+ledger suite; seeded faults; zero-call denials; audit fault injection. | G | L → S | 2 |
| Verify | 15 Replay/crash/cancel/concurrency/approval/injection negatives; both-host isolation harness. | H | L → S | 2 |
| Release | 16 Operator docs, exact limits, rollout/rollback, static import/dependency/line-cap gate. | G | L → S | 2 |

Estimate: 32 build/review calls + 8 reserved repair/review calls = 40. Deterministic tests cost zero model calls. Add up to 8 cheap transport probes: haiku/gpt-5.4-mini, synthetic input, $0 eligibility, quota permitting. Total ceiling estimate 48; pause and re-estimate beyond it. Quota exhaustion never escalates to frontier.

Release slice only when ≥1 allowed invocation and ≥1 denial have complete decision traces; old acceptance tests pass; required negatives pass; eight runtime caps hold. Finite hard-token requests remain explicit denial until separately proven transport support; legacy host-wide enforcement remains deferred. No claimed completion of every CEO objective.

## 7 QUESTIONS FOR CEO

None blocking the first slice. Conservative defaults above keep unsupported/high-risk paths closed; no new provider disclosure grant inferred.
