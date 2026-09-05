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
