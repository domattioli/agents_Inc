# Budget mode — quota-aware delegation

**Status**: Active. Supplements `routing-policy.md`, which governs normal operation.
**Purpose**: A mode the operator turns on when approaching an Anthropic usage limit, or when starting long-running work that shouldn't consume the whole allowance. It shifts as much work as possible onto backends billed against a different quota, and pivots automatically when any one of them runs dry.

## The premise, and its limit

Standard mode optimizes for quality per task. Budget mode optimizes for **Anthropic tokens not spent**, accepting more supervision cost in exchange.

This is a real trade, not a free win. Measured on this project, building an identical dashboard cost 15,221 Gemini tokens, 61,425 Codex tokens, or 79,077 Haiku tokens. The external backends were 5.2× and 1.3× cheaper in raw count and consumed zero Anthropic budget — but the external outputs also needed more of my verification, because I cannot see what they read. Budget mode moves cost from the token bill to the review loop. Use it when the token bill is the binding constraint, not when correctness is.

## Every backend has a ceiling

The pivot logic exists because **no backend here is unlimited**, including the ones that feel free.

| Backend | Quota shape | Reset | Observed failure signal |
|---|---|---|---|
| Gemini flash / flash-lite | free-tier requests per minute and per day | daily, UTC midnight | `429` with `RESOURCE_EXHAUSTED` / `Quota exceeded for metric ... free_tier_requests` |
| Gemini pro tier | **`limit: 0` on this account** — not available at all | n/a | `429 ... limit: 0, model: gemini-3.1-pro` |
| Gemini (any) under load | transient capacity, not quota | seconds to minutes | `503` "experiencing high demand" |
| Codex / ChatGPT Plus | rolling usage windows | ~5h rolling, plus weekly | rate-limit text on stderr, non-zero exit |
| Mistral | API quota/billing limits | provider-defined | HTTP `429` / rate-limit response |
| Claude Haiku / Sonnet / Opus 5 / Fable 5 | plan session + weekly limits, shared across tiers | per plan | harness-level limit message |

Two consequences worth internalizing. Gemini's `deep` tier is unusable on your account, so any policy row that routes "hard analysis" there is wrong — corrected below. And a Gemini `503` is **not** a quota failure; retrying it is correct, while retrying a `429` just burns the remaining allowance faster.

## Routing ladder

Each row is an ordered fallback chain. Take the leftmost backend not in cooldown.

| Task class | 1st | 2nd | 3rd | Why this order |
|---|---|---|---|---|
| Bulk digest, summarize a corpus | Gemini flash | Codex | Haiku | 1M context absorbs in one pass what Codex needs many reads for |
| High-volume shallow triage | Gemini flash-lite | Gemini flash | Haiku | Work is shallow; tier quality doesn't bind |
| Log / trace / stack analysis | Gemini flash-lite | Gemini flash | Codex | Large blob, mechanical extraction |
| Repo survey, cross-file tracing | Codex | Haiku | Gemini + explicit files | Codex reads the tree itself; Gemini needs files hand-fed |
| Second-opinion debugging | Codex | Sonnet | Gemini flash | Codex can run and reproduce locally |
| Code review / critique | Codex | Sonnet | Haiku | Reading code, not writing it — safe to externalize |
| **Writing / editing code** | Haiku | Gemini flash | Codex → then ask | Operator ratified external code authorship in budget mode on 2026-09-02, overriding the prior Claude-only rule. When all three are cooling, stop and ask rather than escalating |
| Mechanical text transform | Gemini flash-lite | Haiku | — | Rename, reformat, extract; no judgment |
| Orchestration — decomposing work, dispatching subagents, holding the thread | Fable 5 | Opus 5 | Sonnet 5 | Fable 5 is the orchestrator tier; Opus 5 is the fallback when Fable is unavailable or its cost is not warranted |
| Planning, synthesis, conversation | Sonnet 5 | Opus 5 | Fable 5 | Ascending cost — budget mode starts cheap and escalates only when the cheaper tier visibly fails |
| Final verification of delegated work | **never delegated** | | | The check must not share a failure mode with the thing checked |

One row never moves regardless of budget pressure: **verification stays with me.** A backend that cannot see what another backend read is not an independent check, so the reviewer must never be drawn from the same pool as the author.

Code authorship *does* move in budget mode. The operator ratified this on 2026-09-02, overriding the earlier Claude-only rule. The trade being accepted: external models write code without the repo conventions a Claude subagent inherits from `CLAUDE.md`, so their output needs closer review. That review is the price of the token saving, and it is mine to pay — which is why the verification row above stays fixed.

## Pivot rules

**On `503` or a transport error** — transient. Retry the same backend 3 times with 5s / 15s / 45s backoff. Only then pivot. Do not mark a cooldown; nothing is exhausted.

**On `429` / quota exhausted** — hard. Mark the backend in cooldown immediately and pivot on the next call without retrying. Retrying a quota error consumes allowance you don't have.

**Cooldown durations**: Gemini until the next UTC midnight (free tier resets daily). Codex and Mistral use 60 minutes. Claude tiers follow whatever the harness reports.

**When every backend in a chain is cooling down**, stop and tell the operator which quotas are exhausted and when each returns. Do not silently escalate to a more expensive backend — that defeats the mode.

**Cooldowns are recorded**, not remembered, in `~/.codex-bridge/backend-health.json`, so the state survives between sessions and a fresh session doesn't re-hammer an exhausted backend to rediscover it.

## Orchestrator tier and its fallback

Fable 5 is the orchestration tier: it holds the task thread, decomposes work, and dispatches. Opus 5 is its fallback, and the direction of fallback differs by mode.

In **standard mode** the chain descends by capability — Fable 5, then Opus 5, then Sonnet 5. You start with the most capable orchestrator and step down only if it is unavailable.

In **budget mode** the chain ascends by cost — Sonnet 5, then Opus 5, then Fable 5. You start cheap and escalate only when the cheaper tier demonstrably fails at the task, not preemptively.

The same three models, ordered oppositely, because the modes optimize for opposite things. Fable 5 at $10/$50 per MTok is twice Opus 5's rate, so in a mode whose entire purpose is conserving allowance it is the last resort rather than the default.

Orchestration never leaves Anthropic in either mode. The orchestrator holds the conversation context, and that context is what the external backends cannot see — exporting it would cost more than the delegation saves.

## Ultra mode — no Anthropic delegation

Ultra mode is the strict form of the same cost-conserving idea. Where budget mode prefers cheaper routes but retains Anthropic models in its fallback chains, ultra mode permits only Gemini flash, Gemini flash-lite, Codex, and Mistral. Its purpose is to spend zero Anthropic allowance on delegated work, so exhaustion stops the route rather than escalating silently to an Anthropic model.

The ultra chains are deliberately short and explicit. Each row remains an ordered fallback chain, taking the leftmost backend not in cooldown.

| Task class | Ultra chain |
|---|---|
| Bulk digest, summarize a corpus | Gemini flash → Codex |
| High-volume shallow triage | Gemini flash-lite → Gemini flash |
| Log / trace / stack analysis | Gemini flash-lite → Gemini flash → Codex |
| Repo survey, cross-file tracing | Codex → Gemini flash |
| Second-opinion debugging | Codex → Mistral → Gemini flash |
| Code review / critique | Codex → Mistral → Gemini flash |
| Writing / editing code | Codex → Mistral → Gemini flash → ask |
| Mechanical text transform | Gemini flash-lite → Gemini flash |
| Planning, synthesis, conversation | Codex → Mistral → Gemini flash |

The `ask` terminal in the code chain means stop and ask the operator; it is not a model and therefore does not violate ultra's restriction. If every backend in another ultra chain is cooling down, `route.sh` prints `NONE` and exits 3. It does not consult a budget or standard chain afterward.

Orchestration is the one class ultra refuses outright. As the preceding section explains, the orchestrator must retain the session's conversation context, and no external backend can see it. Because every eligible orchestrator is Anthropic, `route.sh pick orchestrate` reports that orchestration stays in the current session and exits 4 instead of selecting a backend.

The router also checks the provenance of a selected backend immediately before returning it. If a future chain edit causes ultra to select Haiku, Sonnet, Opus, or Fable, that defensive guard names the backend and class and exits 5. The guard is unreachable with the current chains; its purpose is to make an unsafe edit fail loudly instead of quietly consuming Anthropic allowance.

Callers must distinguish the router's exit codes rather than treating every non-zero result as the same failure.

| Exit code | Meaning |
|---|---|
| 2 | Unknown task class or invalid `CODEX_BRIDGE_MODE` value |
| 3 | Every backend in the selected chain is cooling down |
| 4 | Orchestration was refused in ultra mode and remains in the current session |
| 5 | The defensive ultra guard refused an Anthropic backend |

## Turning modes on

Routing mode is explicit, never inferred. `CODEX_BRIDGE_MODE` accepts `standard`, `budget`, or `ultra`, and defaults to `standard`; any other value is an error and exits 2. The operator enables a conserving mode, and I do not switch modes based on my own guess about their remaining allowance. When budget or ultra is on, I state the backend used in each report, so the audit trail survives the mode change.
