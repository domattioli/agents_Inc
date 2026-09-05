# HOW IT WORKS

Caveman ultra. Reader = operator or agent. Newcomer → read `START-HERE.md` first.

## One sentence

Cheap models do work. Expensive model supervises. This repo = plumbing + discipline to make that safe.

## Two halves. Do not confuse them.

| half | file | owns | question it answers |
|---|---|---|---|
| mechanism | `skills/codex-bridge/` | transport, routing, retries, job state, cost logging | HOW do I send work out |
| judgment | `skills/workerbee/` | tier choice, trust, verification, honesty | SHOULD I, and do I believe the answer |

Mechanism has no opinions. Judgment has no code. Keep it that way → each stays replaceable.

## Parts

```
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

`bridge.py` = separate thing. HTTP server, persistent codex thread, for remote clients. Not needed for local delegation. Ignore unless serving a phone.

## Flow. One job.

1. classify task → task class (digest / triage / code review / write code / …)
2. `route.sh pick <class>` → backend. Skips backends in cooldown.
3. `agent.sh submit --backend <b> --wait "<prompt>"` → job id
4. job runs. transient fail → auto retry. quota fail → cooldown, no retry.
5. `agent.sh result <id>` → output + `result.json`
6. YOU verify. See `## Trust` below.
7. usage logged → cost visible later

## Money

Three billing pools. Never merge them in your head.

| pool | models | shape |
|---|---|---|
| Anthropic plan | opus / sonnet / haiku / fable | session + weekly limits |
| ChatGPT plan | astra / sol / terra / luna | rolling ~5h + weekly windows |
| per-token API | gemini free tier, mistral, openrouter | requests/day or $ per token |

Budget mode = shift work off pool 1 onto pools 2 and 3.

Not free. Real trade: token bill ↓, verification effort ↑. Measured — same dashboard cost 15,221 Gemini tokens vs 79,077 Haiku tokens, but external output needed more checking because you cannot see what it read. Use budget mode when the bill binds. Not when correctness binds.

**Unknown price ≠ zero.** Coercing null→0 once inflated a savings figure 29x ($1.15 → $33.06). Free models priced `0.0` explicitly. Unknown left absent, excluded from sums, headline marked partial (`~$1.15+?`). Plan-based access has no per-token price → leave absent. Writing `0.0` there is a lie in the other direction.

## Trust. The part that actually matters.

Delegate reports GREEN. Believing it is the expensive mistake.

Real, one session, three times: delegate printed the numbers it INTENDED, not the ones it MEASURED. Claimed columns `0 12 44 91 124`. Actual `0 12 49 122 214 329 446`. Nothing aligned.

Rules:
- YOU write the verifier. Outside delegate's workspace. Dispatch says DO NOT EDIT IT.
- Report must carry harness output + exit code. Claim without output = RED.
- Self-test the harness both ways first. Prove GREEN on known-good, RED on known-bad. Unfalsifiable harness worse than none.
- Passing harness still not proof. Check its granularity matches the claim's. One passed while measuring 4 boundaries on rows holding 7 items.
- Re-run the delegate's own check yourself. Cheap. Catches most of it.

Full discipline → `../skills/workerbee/SKILL.md`.

## Sandbox gotchas. Bite every time.

- `workspace-write` → NO network. HTTP buddies die `Could not resolve host`. Fix: `-c 'sandbox_workspace_write.network_access=true'`
- same sandbox blocks `.git/index.lock` → delegates CANNOT commit. Expect `Operation not permitted`. Have them report `BLOCKED-SANDBOX`; you land the commit.
- outside a git repo → `--skip-git-repo-check` required
- review-only scope → `--sandbox read-only`. Cheaper than trusting "do not edit". Sandbox guarantees it; the model does not.

## Irreversible actions

Number the gates. Withholding = SUCCESS outcome. Firing on a red gate = only unforgivable failure. Ambiguous gate → RED.

Guards live on the REMOTE side. Launching session dies long before a remote job does. A guard in the launcher protects nothing.

If unsure whether a dispatch landed → CHECK before re-firing. Double dispatch = double cost.

## Stateless buddies

Gemini / Mistral / OpenRouter one-shots see ONLY your prompt. No tools. No repo.

Describe a function to them → they invent a plausible one that does not exist. Paste verbatim source, real rows, actual output.

Buddy output never = evidence. Verify against the real system, with a citation.

Providers fail constantly. Verbatim:
```
ask_openrouter: API error: Upstream error from Nvidia: Service temporarily overloaded
ask_gemini: API error: This model is currently experiencing high demand.
ask_mistral: API error: Not enough capacity available for this request, please retry later.
```
Fail over across family. Never stall on one dead provider.

Gemini `503` = capacity → retry correct. Gemini `429` = quota → retry burns remaining allowance faster. Different failures. Different responses.

## Secrets

Keys come from a `.env` file. Never on a command line. Never echoed to a log. Never pasted into a model prompt.

Name forbidden paths explicitly in every dispatch — do not assume the delegate infers them.

Operator pastes a live key into chat → say so, recommend rotation, keep using the file.

## Where to go next

- extend it → `EXTENDING.md`
- new human → `START-HERE.md`
- full supervision discipline → `../skills/workerbee/SKILL.md`
- routing table → `../skills/codex-bridge/reference/routing-policy.md`
- budget mode detail → `../skills/codex-bridge/reference/budget-mode.md`
