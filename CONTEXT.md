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
| **Tier** | Legacy word. Use **Rung**: Executive, Orchestrator, Workhorse, or Grunt. |
| **Mode** | lawyer / scientist / engineer. Changes required fields and forbidden actions, never data policy. |
| **Acceptance user** | Tim (lawyer, documents to cited brief) and Dom (engineer/scientist tasks). Both day 1. |
| **Node** | One delegated job recorded in the dispatch graph ledger; identity = id; carries model, tier, task, provider, parent_id, edge_type, status, seconds, subscription_calls, gate_reason, timestamp. |
| **Edge** | Directed relationship in dispatch graph, implied by child node's parent_id + edge_type (not separately stored); types: reviews, corrects, probes, depends-on, seconds. |
| **Run** | Groups of nodes from one brief or one doctor preflight (identified by run_id); groups all worker, reviewer, and correction nodes for one top-level invocation. |
| **Run tree** | The nodes of one run arranged as a single rooted tree. Root = the orchestrating act that received the ask; every other node descends from it via parent_id. Chosen over a forest (CEO 2026-09-06) so fan-outs can be planned and read as one structure. |
| **Family** | One orchestrator node plus every node descending from it. The run tree is the top family; families nest. Alias: fam. Synonyms retired: fan-out (the act of dispatching N children), delegation (one parent→child edge). |
| **Orchestrator** | Any agent that dispatches children. Recorded as its own node (task orchestrate, provider = its host) so it can root a family. Depth rules count from the nearest orchestrator. |
| **Lead** | The agent the CEO addresses for a run. May root the run tree. It has Task Authority only when policy grants it; a frontier model has no automatic final say. |
| **Second** | An agent that helps a run. It has no automatic authority from being second, vendor, or rung. Any Task Authority must come from policy and be recorded. Structurally it may be a child with edge type `seconds`; graph shape does not grant authority. |
| **Task Authority** | A policy-granted role with final say on one task, inside recorded limits. It may accept, reject, or ask for revision. It cannot break policy, grow scope, or approve blind. An untrusted free model can never hold it. |
| **Capability Escalation** | Send the same task to a stronger allowed model. Task Authority stays with its holder, but only if that holder can judge the result. |
| **Authority Reassignment** | An explicit, recorded move of Task Authority to a pre-approved new holder. Use it when the old holder cannot continue or cannot judge the work. |
| **Promotion** | Retired for new decisions. Use Capability Escalation and/or Authority Reassignment. Old D27 uses remain historical record. |
| **Rung** | A cost and capability class only. Four rungs: Executive, Orchestrator (aka Supervisor), Workhorse, and Grunt. A rung, vendor, or pair gives no automatic Task Authority or special access. Policy chooses allowed models from any vendor's whole model list. Renamed 2026-09-07 (D34): top rung Supervisor -> Executive; Orchestrator gained Supervisor as a synonym. Ranking table of record: docs/governance/ROUTING-RANKING.md. |
| **Second opinion** | The same task sent to the paired model without the first answer. A Supervisor compares both outputs afterward. Tests independent reasoning; never asks one model to approve another's conclusion. |
| **Free grunt** | Any GPT model outside the ladder (gpt-5.4-mini included), every OpenRouter free model, Gemini free tier, Mistral free tier. $0 only. Never a Codex subscription call. In budget modality free grunts fill workhorse and grunt slots and review each other across upstream vendors. Coding permission is scoped: well-scoped, small jobs only — high volume of small diffs, never a large or architecturally significant change (CLAUDE.md Coding dispatch labor rule). |
| **Run spec** | Saved routing input for one run: task and pass rule; Task Authority and limits; authority-move rule; policy version; allowed models; hard limits; budget and deadline; ranking order; retry and fallback rule. Missing ranking order makes the run invalid. |
| **Derivation** | From a saved run spec and model-list snapshot: remove hard-limit failures; rank kept candidates by the stated order; break ties by model ID. Save every candidate and keep/drop reason, the pick, snapshot ref, retries, and every Authority Reassignment. This gives policy-choice determinism and replay, not deterministic model output or live availability. |
| **Modality** | Ideal or budget. Ideal = the full derived tree. Budget = same spec and shape, but workhorse and grunt slots filled by free grunts through OpenRouter, ladder models kept for supervisor, orchestrator, review, and fallback. |
| **Scout** | A cheap, bounded reconnaissance dispatch sent *before* committing real work, to answer a feasibility or existence question: does X exist, what shape is it, is it worth a real dispatch. Produces a finding, never a deliverable: a scout may not write to the repo, and its report is unverified by construction (same bar as any delegate report). Whoever acts on a scout finding re-derives it. Scouting is a mode of dispatch, not a rung. |
| **Scout node** | The ledger record of a scout. Carries edge type `probes`, the same type already used for doctor preflight probes (`parent_id` None, projected through `legacy_parent`). A scout never becomes a spawn parent: it takes no `lineage` row, so recon is auditable in the run without appearing as an ancestor of the work it informed. |
| **Scout roster** | Who may scout. Default: free grunts (OpenRouter free, Gemini free, Mistral free, gpt-5.4-mini) — text-in/text-out recon over a supplied blob. When the recon needs tools (walk a repo, read a tree, run a command) it goes to the Grunt rung, haiku or luna, because free grunts have no tools. Never Workhorse rung or above: recon that needs sonnet/terra is not recon, it is the work, and belongs in a real run spec. Sole exception is a Lead assignment with a recorded gate reason (D27 promotion (c)). |
| **Budget review** | In budget modality a free grunt is reviewed by a free grunt from a different upstream vendor (OpenRouter, Gemini, Mistral pooled). Deterministic pick from the catalog's upstream-vendor field. Quota-paused reviewer falls back to the ladder grunt (haiku or luna). |
| **Finding** | Lint result from dispatch graph ledger; carries rule (depth, same_vendor_review, frontier_without_gate), node_ids, and human-readable message. |
| **Ledger** | Append-only JSONL file (`<workspace>/.workerbees/ledger.jsonl`) recording every delegated job as a node; idempotent by node id on read (dedup merges dispatch + return records). |
| **Agent** | Registered identity in the governance graph; carries id, name, type, capabilities, clearance, enabled flag. Model id is not an agent id. |
| **Capability** | A named operation an agent may perform (e.g. `extract.markdown`, `review.claims`). Unsupported ones — deploy, delete, send, grant, tools, web — are registered as disabled and always denied. |
| **Relationship** | Directed edge between two agents (`delegates_to`, `requests`, `probes`) with allowed params. Policy maps a `request` envelope to `delegates_to`; absent edge denies. |
| **Decision** | Verdict of one policy evaluation: allowed, decision_id, reason_code, reason, policy_version, checked_rules. Persisted before dispatch, for denials as well as allows. Never carries prompts, output, or secrets. |
| **Gateway** | The single dispatch boundary. Validates the envelope, authorizes it, reserves budget, invokes the adapter, records the decision and the ledger node, releases in `finally`. Permission from the gateway is never a claim about output quality. |
