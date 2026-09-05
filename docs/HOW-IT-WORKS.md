# HOW IT WORKS

- Reader
  - **Audience**
    - This is for an operator or agent.
  - **Prerequisite**
    - Newcomers should read `START-HERE.md` first.

## System

- Delegation system
  - **Work**
    - Cheap models do the work.
  - **Supervision**
    - An expensive model supervises.
  - **Purpose**
    - The repo combines plumbing with discipline for safe delegation.

## Two halves

| half | file | owns | question it answers |
|---|---|---|---|
| mechanism | `skills/codex-bridge/` | transport, routing, retries, job state, cost logging | HOW do I send work out |
| judgment | `skills/workerbee/` | tier choice, trust, verification, honesty | SHOULD I, and do I believe the answer |

- Boundary
  - **Mechanism**
    - It has no opinions.
  - **Judgment**
    - It has no code.
  - **Reason**
    - Each half stays replaceable.

## Parts

```text
you (orchestrator)
  │
  ├─ route.sh pick <class>      → which backend for this task class
  │
  ├─ agent.sh submit            → queue job, get id
  │     ├─ codex  → codex CLI      (OpenAI, ChatGPT plan)
  │     ├─ gask.sh → Gemini API     (free tier)
  │     ├─ mask.sh → Mistral API    (paid key)
  │     └─ oask.sh → OpenRouter      (free models ONLY, spend guard)
  │
  ├─ agent.sh wait/result       → saved stdout + result.json
  │
  ├─ usage_db.py                → per-call token log → ~/.codex-bridge/usage.db
  └─ dashboard.py / usage_report.sh → what it cost
```

- Remote bridge
  - **File**
    - `bridge.py` is a separate HTTP server with a persistent codex thread for remote clients.
  - **Local use**
    - Local delegation does not need it.
  - **Exception**
    - Use it when serving a phone.

## One-job flow

- Dispatch
  - **Steps**
    - `route.sh pick <class>` classifies the task and skips backends in cooldown.
    - `agent.sh submit --backend <b> --wait "<prompt>"` queues the job and returns its id.
    - The job retries transient failures automatically and places quota failures in cooldown without retrying.
    - `agent.sh result <id>` returns output and `result.json`.
    - `poll.sh` polls the job for the entire run.
    - You verify the result.
    - Usage is logged for later cost reporting.

## Polling

- Job observation
  - **Rule**
    - Poll every dispatch that outlives one tool call.
  - **Poll command**

```bash
scripts/poll.sh --pid-match <pat> --log <stderr> --out <stdout>
```

  - **Watch command**

```bash
scripts/watch.sh <stderr>
```

  - **Boundary**
    - Poll reports state to the supervisor. Watch streams content to a human in another pane.
    - Never pipe a log into supervisor context because it spends the tokens delegation was meant to save.
  - **States**
    - `RUNNING`, `QUIET`, `RESUMED`, `DONE`, `DIED`, and `TIMEOUT` are emitted only on change.
  - **Exit status**
    - Exit 0 means returned, not verified.
  - **DIED**
    - `DIED` means the process is gone and output is empty.

## Money

- Billing pools
  - **Subscriptions**
    - Anthropic covers opus, sonnet, haiku, and fable through session and weekly limits.
    - ChatGPT covers astra, sol, terra, and luna through rolling ~5h and weekly windows.
  - **API**
    - Gemini free tier, Mistral, and OpenRouter use requests per day or dollars per token.
  - **Budget mode**
    - It shifts work from pool 1 to pools 2 and 3.
    - Token cost falls while verification effort rises.
  - **Measurement**
    - The same dashboard recorded 15,221 Gemini tokens versus 79,077 Haiku tokens, while the external output required more checking because its input was not visible.
  - **Price rule**
    - Unknown price is not zero.
  - **Evidence**
    - Coercing null to 0 inflated a savings figure 29x, from $1.15 to $33.06.
    - Free models use `0.0`. Unknown prices stay absent, and plan-based access has no per-token price.

## Trust

- Independent verification
  - **Failure**
    - A delegate can report GREEN while printing intended measurements instead of actual measurements.
  - **Observed data**
    - One session claimed columns `0 12 44 91 124`. The actual values were `0 12 49 122 214 329 446`.
  - **Verifier**
    - You write it outside the delegate’s workspace and tell the delegate not to edit it.
  - **Evidence**
    - A report needs harness output and an exit code. A claim without output is RED.
  - **Harness gate**
    - Self-test the harness with known-good and known-bad inputs before using it.
  - **Granularity**
    - Check that the harness measures the same granularity as the claim.
  - **Recheck**
    - Re-run the delegate’s own check yourself.
  - **Reference**
    - Full discipline is in `../skills/workerbee/SKILL.md`.

## Sandbox constraints

- Execution
  - **Network**
    - `workspace-write` blocks network access. HTTP buddies fail with `Could not resolve host`.
  - **Workaround**
    - Use `-c 'sandbox_workspace_write.network_access=true'`.
  - **Git**
    - The same sandbox blocks `.git/index.lock`, so delegates cannot commit. Expect `Operation not permitted` and have them report `BLOCKED-SANDBOX`.
  - **Repository**
    - Outside a git repo, use `--skip-git-repo-check`.
  - **Review**
    - Use `--sandbox read-only` for review-only work.

## Irreversible actions

- Gates
  - **Counting**
    - Number the gates.
  - **Withholding**
    - Withholding an action after a red gate is the successful outcome.
  - **Ambiguity**
    - An ambiguous gate is RED.
  - **Location**
    - Guards belong on the remote side because a launcher guard cannot protect a remote session.
  - **Duplicate dispatch**
    - Check whether an uncertain dispatch landed before firing it again.

## Stateless providers

- One-shot behavior
  - **Context**
    - Gemini, Mistral, and OpenRouter receive only the prompt, with no tools or repository.
  - **Evidence**
    - Paste source, real rows, and actual output instead of describing a function.
  - **Verification**
    - Buddy output is never evidence. Verify it against the real system with a citation.
- Provider failures
  - **Failover**
    - Fail over across provider families.
  - **Signals**

```text
ask_openrouter: API error: Upstream error from Nvidia: Service temporarily overloaded
ask_gemini: API error: This model is currently experiencing high demand.
ask_mistral: API error: Not enough capacity available for this request, please retry later.
```

  - **Gemini**
    - `503` means capacity and merits a retry.
    - `429` means quota and a retry burns remaining allowance faster.

## Secrets

- Key handling
  - **Source**
    - Keys come from a `.env` file.
  - **Prohibition**
    - Never put keys on a command line, echo them to a log, or paste them into a model prompt.
  - **Dispatch**
    - Name forbidden paths explicitly in every dispatch.
  - **Exposure**
    - If an operator pastes a live key into chat, recommend rotation and continue using the file.

## Legacy wrappers for optional providers

`workerbees/adapters/` ships claude + codex only. Gemini / Mistral / OpenRouter reach the fleet through the older `codex-bridge` shell wrappers, not through an adapter module:

| provider | wrapper | key file (or env var) |
|---|---|---|
| Gemini | `skills/codex-bridge/scripts/gask.sh` | `~/.codex-bridge/gemini-key` (`GEMINI_API_KEY`) |
| Mistral | `skills/codex-bridge/scripts/mask.sh` | `~/.config/devstral/api_key` |
| OpenRouter | `skills/codex-bridge/scripts/oask.sh` | `~/.codex-bridge/openrouter-key` (`OPEN_ROUTER_API_KEY`) |

- Optional-provider access
  - **Key location**
    - Keys live in those per-provider files. There is no `~/.config/workerbees/.env`, and its absence does not mean keys are absent.
  - **Usage**

```bash
bash skills/codex-bridge/scripts/gask.sh --tier digest "prompt"
```

    - `--file PATH` attaches context.
    - `oask.sh` refuses non-`:free` models through its spend guard.
  - **Authorization**
    - D7 denies confidential input to an optional provider until `.workerbees/authorization.json` authorizes that workspace.
    - Non-confidential extract and summarize work is allowed.

## Next docs

- `EXTENDING.md` covers extensions.
- `START-HERE.md` serves new humans.
- `../skills/workerbee/SKILL.md` contains the supervision discipline.
- `../skills/codex-bridge/reference/routing-policy.md` contains routing.
- `../skills/codex-bridge/reference/budget-mode.md` contains budget mode.
