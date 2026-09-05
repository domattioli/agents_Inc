# Delegation Routing Policy

**Status**: Active. Operator ratified automatic routing 2026-09-02.
**Scope**: Governs which backend performs which class of work for this operator's local sessions.

## The organizing principle

Delegation saves context only when the bulk material never enters the Claude conversation. It does not save anything because "a cheaper model did the work." If Claude reads forty files in order to hand them to another model, the cost has already been paid and the delegation is theater.

Every route below is therefore judged by one question: **can the worker fetch its own data?** A backend that can is a real offload. A backend that cannot is only useful when a script fetches the data on its behalf, so the bytes live in the script's memory rather than in a context window.

## Backend characteristics

| Backend | Fetches own data | Sees this conversation | Marginal cost | Trains on input |
|---|---|---|---|---|
| Claude main session | Yes | Yes — it *is* the conversation | Anthropic tokens, highest tier | No |
| Haiku subagent | Yes | No — brief only | Anthropic tokens, low tier | No |
| Codex (GPT) | Yes — native filesystem access | No | ChatGPT Plus quota | No (paid tier) |
| Gemini | No — `gask.sh` reads and posts on its behalf | No | Free tier | **Yes** |
| Mistral | No — `mask.sh` reads and posts on its behalf | No | Mistral API quota/billing | Not established here |

Two consequences follow directly from this table and drive most routing decisions.

Gemini trains on submitted input on the free tier. That single fact excludes it from anything proprietary, client-related, or personal, regardless of how well it would otherwise fit the task.

Codex's constraint is a rate-limit window rather than a dollar amount. Heavy fan-out does not produce a surprise bill; it produces a throttle in the middle of work. Pace accordingly, and prefer one large instruction over ten small ones.

## Routing table

| Class of work | Route | Rationale |
|---|---|---|
| Repo survey, "what does this subsystem do", cross-file tracing | Codex | Reads the tree itself; the persistent thread accumulates understanding across follow-ups |
| Very large single blobs — logs, traces, transcripts, dumps | Gemini (`digest` tier) | Million-token context absorbs in one pass what would take Codex many reads |
| High-volume mechanical triage over many small inputs | Gemini (`cheap` tier) | Free and fast; the work is shallow enough that tier quality does not bind |
| Hard analysis over large material | Gemini (`digest` tier) | The `deep`/pro tier returns `limit: 0` on this account — it is not available on the free tier, verified 2026-09-02 |
| Stuck debugging, independent second hypothesis | Codex | Can actually run and reproduce locally, not merely read |
| **Writing or editing code** | **Haiku subagent** | Binding rule in the operator's `CLAUDE.md`. Not negotiable by this policy. |
| Orchestration — decomposition, dispatch, holding the thread | Fable 5, falling back to Opus 5 | Orchestrator tier; the fallback applies when Fable is unavailable or its cost is unwarranted |
| Planning, architecture, review, integration, verification | Claude main session | Requires conversation context, which cannot be exported |
| Anything sensitive, proprietary, or personal | Codex or Claude only | Gemini free tier trains on input |
| Anything depending on what was said earlier in this conversation | Claude main session | The other backends cannot see it, and summarizing it for them costs the tokens the delegation was meant to save |

## Ultra routing

`CODEX_BRIDGE_MODE=ultra` is the strict no-Anthropic delegation mode. It routes only to Gemini flash, Gemini flash-lite, Codex, and Mistral. The Mistral key does not currently expose Devstral; the coding tier therefore uses the available `codestral-latest` model instead. The chains below are the exact order used by `route.sh`; each route takes the first backend that is not in cooldown.

| Task class | Ultra chain |
|---|---|
| `digest` | Gemini flash → Codex |
| `triage` | Gemini flash-lite → Gemini flash |
| `logs` | Gemini flash-lite → Gemini flash → Codex |
| `survey` | Codex → Gemini flash |
| `debug` | Codex → Mistral → Gemini flash |
| `review` | Codex → Mistral → Gemini flash |
| `code` | Codex → Mistral → Gemini flash → ask |
| `transform` | Gemini flash-lite → Gemini flash |
| `plan` | Codex → Mistral → Gemini flash |
| `orchestrate` | Refused; remains in the current session |

The `ask` terminal stops routing and asks the operator; because it is a human decision point rather than a model, it remains valid in the ultra code chain. Orchestration is different: it holds this session's conversation context, which no external backend can see, so ultra refuses to delegate it and exits 4. When an ordinary ultra chain is exhausted, the router prints `NONE` and exits 3 instead of falling through to an Anthropic backend.

A defensive provenance check also refuses any Anthropic backend that a future ultra chain might accidentally yield. That path exits 5 and should be unreachable with the chains above.

## What is never delegated

Verification. The main session checks load-bearing claims itself, because a backend that cannot see what another backend read is not an independent check.

Code authorship is Claude-first in standard mode (Haiku subagent). In **budget mode** it may fall through to Gemini and then Codex — see `budget-mode.md`; the operator ratified that on 2026-09-02.

Work requiring conversation context stays in the main session. Exporting that context defeats the purpose.

Sensitive material never reaches Gemini's free tier.

## Verification obligation

Delegated output is unverified evidence, not fact. The main session cannot see what Codex read or what Gemini was given, so a returned claim carries no more authority than an assertion from a stranger who has seen the code.

Any load-bearing claim — one that will change code, a decision, or a report to the operator — is checked locally before it is acted upon. Cheap checks suffice: read the cited file, run the test, grep for the symbol. The point is that the check happens, not that it is thorough.

This obligation has already earned its place. Two defects in this project's own construction passed a subagent's self-reported smoke tests and were caught only by reading the code afterwards.

## Auditability

Routing is automatic; the operator is not asked to approve each delegation. In exchange, Claude states which backend it used when reporting results, so data egress remains reconstructable after the fact. The usage ledger at `~/.codex-bridge/usage.jsonl` records volume per backend and model, giving a second, independent record of what went where.

## Sandbox scope — what it does and does not bound

`bridge.py` passes `-s <mode>` to every Codex invocation, and this is enforced. Verified 2026-09-02: under `read-only`, Codex attempting to create a file reports "The write was denied by the read-only sandbox" and the file does not appear.

**The sandbox bounds writes only. Reads are unbounded.** Also verified the same day: under `workspace-write`, Codex successfully listed `~/.ssh` (14 entries), and it did so again with `sandbox_permissions=[]`. There is no CLI flag that restricts read access. `--workdir` sets where Codex starts looking, not what it is permitted to open.

The practical consequence: **anything readable by your user account is readable by Codex**, including `~/.codex-bridge/token` — the bridge's own credential — and any SSH or cloud keys. A prompt-injection payload in a file Codex is asked to summarize could induce it to read a secret and return it in its response.

Mitigations that actually apply, in order of effect: keep the bridge bound to loopback and do not expose it through a tunnel; treat every credential on this machine as visible to any Codex call; rotate anything that passes through a session transcript. Running Codex as a separate restricted user would close it properly, and is not currently set up.

## Credentials

The Codex bridge token and the Gemini key both live in `~/.codex-bridge/`, mode 600, outside any project tree. The bridge token confers shell-equivalent authority on the host machine: anyone holding it can cause arbitrary local command execution through Codex. Treat it as a private key, not as an API token.
