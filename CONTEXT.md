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
| **Edge** | Directed relationship in dispatch graph, implied by child node's parent_id + edge_type (not separately stored); types: reviews, corrects, probes, depends-on, seconds. |
| **Run** | Groups of nodes from one brief or one doctor preflight (identified by run_id); groups all worker, reviewer, and correction nodes for one top-level invocation. |
| **Run tree** | The nodes of one run arranged as a single rooted tree. Root = the orchestrating act that received the ask; every other node descends from it via parent_id. Chosen over a forest (CEO 2026-09-06) so fan-outs can be planned and read as one structure. |
| **Family** | One orchestrator node plus every node descending from it. The run tree is the top family; families nest. Alias: fam. Synonyms retired: fan-out (the act of dispatching N children), delegation (one parent→child edge). |
| **Orchestrator** | Any agent that dispatches children. Recorded as its own node (task orchestrate, provider = its host) so it can root a family. Depth rules count from the nearest orchestrator. |
| **Lead** | The frontier agent the CEO addresses for a run. Roots the run tree, has final say, may direct the Second on how to use its authority. Fable or astra; picked per ask. |
| **Second** | The other frontier agent in a run. Holds real authority over the family (may direct, block, review) but yields to the Lead on any conflict. Structurally a child of the root with edge type `seconds`; authority is expressed in policy (veto over siblings, may root its own sub-family), not in graph shape. Tree preserved. |
| **Promotion** | Moving a task to a costlier tier. Triggers: (a) the current worker is spinning its wheels, meaning two failed checks on the same task, or a provider outage such as a Codex usage-limit pause, which counts as a failed attempt, not a verdict on the model; (c) the Lead assigns it with a recorded gate reason. Never on worker confidence. Sonnet builds only via promotion. |
| **Rung** | Position in the model ladder. Four rungs, each a claude↔codex pair: Executive = fable ↔ astra; Orchestrator (aka Supervisor) = opus ↔ sol; Workhorse = sonnet ↔ terra; Grunt = haiku ↔ luna. Escalation goes one rung up; second opinion goes across to the pair. Renamed 2026-09-07 (D34): top rung Supervisor -> Executive; Orchestrator gained Supervisor as a synonym, same rung, same role. Ranking table of record: docs/governance/ROUTING-RANKING.md. |
| **Second opinion** | The same task sent to the paired model without the first answer. A Supervisor compares both outputs afterward. Tests independent reasoning; never asks one model to approve another's conclusion. |
| **Free grunt** | Any GPT model outside the ladder (gpt-5.4-mini included), every OpenRouter free model, Gemini free tier, Mistral free tier. $0 only. Never a Codex subscription call. In budget modality free grunts fill workhorse and grunt slots and review each other across upstream vendors. |
| **Run spec** | The two names the CEO gives per run: Executive model and Orchestrator model. Everything else in the run tree (Second, workhorses, grunts, reviewers, edges) is derived deterministically from the ladder and the vendor rule. Only Executive and Orchestrator rungs may have children; Workhorse and Grunt are leaves. |
| **Derivation** | From a run spec: Second = Executive's pair; Orchestrator's reviewer = its pair; workhorses and grunts = Orchestrator's vendor, one rung down each, reviewed by their pairs; second opinion = the answerer's pair, blind; promotion = one rung up, same vendor, or the pair if that vendor is quota-paused. The reviewer at every rung is also the fallback for that rung. |
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
