# CONTEXT.md — glossary

Canonical terms for agents_for_dummies. Glossary only; no implementation detail.

| Term | Meaning |
|---|---|
| **Host** | The agent CLI the user talks to. Launch hosts: Claude Code and Codex. |
| **Driver** | The host session that decomposes a task and dispatches workers. |
| **Worker** | A model invocation that receives text on stdin and returns a candidate. No tools. |
| **Reviewer** | A model invocation, from a different vendor than the worker, that checks consequential claims against original sources. |
| **Verifier** | Deterministic code checks (quotes, hashes, anchors, arithmetic). Not a model. |
| **Required provider** | Claude Code and Codex. Subscription login. Setup blocks without them. |
| **Optional provider** | Gemini, Mistral, OpenRouter free tiers. API key. Missing key skips the provider, never blocks setup. |
| **Free** | Zero incremental dollars per task. Subscription-included or free-tier API key. |
| **Spend cap** | Hard $0 per task. Quota exhaustion pauses the job and tells the user. No paid API path exists. |
| **Workspace authorization** | Explicit per-workspace grant permitting confidential inputs to reach optional providers. Default: denied. |
| **Returned** | Worker process exited 0 and produced output. Says nothing about correctness. |
| **Verified** | Returned output passed verifier and reviewer gates. |
| **Needs-review** | Verified checks passed but an unresolved critical issue remains for a human. |
| **Accepted task** | A task whose output reached verified or needs-review with a retained draft. Unit of the cost metric. |
| **Cost metric** | Dollars per accepted task, measured against an all-frontier baseline, with a quality floor of zero false accepts on seeded faults. |
| **Tier** | cheap / mid / frontier. Task routes by rules to a tier, promoted on failed checks, never on worker confidence. |
| **Mode** | lawyer / scientist / engineer. Changes required fields and forbidden actions, never data policy. |
| **Acceptance user** | Tim (lawyer, documents to cited brief) and Dom (engineer/scientist tasks). Both day 1. |
| **Node** | One delegated job recorded in the dispatch graph ledger; identity = id; carries model, tier, task, provider, parent_id, edge_type, status, seconds, subscription_calls, gate_reason, timestamp. |
| **Edge** | Directed relationship in dispatch graph, implied by child node's parent_id + edge_type (not separately stored); types: reviews, corrects, probes, depends-on. |
| **Run** | Groups of nodes from one brief or one doctor preflight (identified by run_id); groups all worker, reviewer, and correction nodes for one top-level invocation. |
| **Finding** | Lint result from dispatch graph ledger; carries rule (depth, same_vendor_review, frontier_without_gate), node_ids, and human-readable message. |
| **Ledger** | Append-only JSONL file (`<workspace>/.workerbees/ledger.jsonl`) recording every delegated job as a node; idempotent by node id on read (dedup merges dispatch + return records). |
| **Agent** | Registered identity in the governance graph; carries id, name, type, capabilities, clearance, enabled flag. Model id is not an agent id. |
| **Capability** | A named operation an agent may perform (e.g. `extract.markdown`, `review.claims`). Unsupported ones — deploy, delete, send, grant, tools, web — are registered as disabled and always denied. |
| **Relationship** | Directed edge between two agents (`delegates_to`, `requests`, `probes`) with allowed params. Policy maps a `request` envelope to `delegates_to`; absent edge denies. |
| **Decision** | Verdict of one policy evaluation: allowed, decision_id, reason_code, reason, policy_version, checked_rules. Persisted before dispatch, for denials as well as allows. Never carries prompts, output, or secrets. |
| **Gateway** | The single dispatch boundary. Validates the envelope, authorizes it, reserves budget, invokes the adapter, records the decision and the ledger node, releases in `finally`. Permission from the gateway is never a claim about output quality. |
