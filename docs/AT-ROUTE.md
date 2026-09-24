# At-route: ask a cheaper model without leaving your session

At-route is a Claude Code `UserPromptSubmit` hook. When a prompt starts with `@<alias>`, the hook sends the question to that model and shows you the answer. The expensive session model never runs. You stay in the same session, keep its context, and pay the cheap model's price for the side question.

Script: [`skills/codex-bridge/scripts/at_route.sh`](../skills/codex-bridge/scripts/at_route.sh).
Smoke test: [`skills/codex-bridge/tests/at_route.smoke.sh`](../skills/codex-bridge/tests/at_route.smoke.sh).

## Lexicon

| You type | Who answers | Does the session model see it? |
|---|---|---|
| `@haiku what does this flag do?` | Haiku | No. Side question. Answer is shown to you only. |
| `@@haiku what does this flag do?` | Haiku | Yes. Answer is injected as context and the session model relays it. |
| `plain prompt` | Session model | Normal turn. Hook stays silent. |

Aliases, case-insensitive:

| Alias | Model | Path |
|---|---|---|
| `haiku` | `claude-haiku-4-5-20251001` | `claude -p` |
| `sonnet` | `claude-sonnet-5` | `claude -p` |
| `opus` | `claude-opus-5-5` | `claude -p` |
| `fable` | `claude-fable-5-1` | `claude -p` |
| `astra` | `gpt-6-astra` | codex-bridge daemon |
| `sol` | `gpt-5.6-sol` | codex-bridge daemon |
| `terra` | `gpt-5.6-terra` | codex-bridge daemon |
| `luna` | `gpt-5.6-luna` | codex-bridge daemon |

Default is the single `@` form. Use `@@` only when the next thing you ask the session model depends on the answer.

## Measured savings

Question: "explain database connection pooling in about 150 words". Measured 2026-09-23 with `claude -p --output-format json`, which reports token usage and cost per call.

| Path | Session-model output tokens | Cost (USD) | Saving |
|---|---|---|---|
| Ask Fable directly | 582 | 0.78 | baseline |
| `@@haiku` (shared, session model relays) | 351 | 0.60 | 23% |
| `@haiku` (side question, session model skipped) | 0 | 0.009 | 99% |

Why `@@` saves so little: the session model still has to write the answer back out, and in the measured run it rewrote the answer instead of relaying it. Output tokens are the expensive part, so the shared form is only worth it when the session model needs the answer in context.

Latency for a short question: about 5 to 6 seconds for both Claude and Codex aliases.

## How it works

1. Claude Code runs every `UserPromptSubmit` hook before the session model sees your prompt, passing the prompt as JSON on stdin.
2. The hook matches `^(@@?)(alias)\s+(question)$`. No match: exit 0, print nothing.
3. Claude aliases run `claude -p "<question>" --model <id>`. Codex aliases run `agent.sh submit --backend codex --model <id> --wait`, then `agent.sh result <job id>` for the answer text.
4. Single `@`: answer goes to stderr and the hook exits 2. Exit 2 blocks the prompt, so the session model never runs, and stderr is shown to you.
5. Double `@@`: answer goes to stdout and the hook exits 0. Stdout becomes extra context for the session model, with a one-line instruction to relay it.
6. On any failure the hook prints the error as context and exits 0, so the session model answers the question itself.

Recursion guard: the hook exports `AT_ROUTE_ACTIVE=1` around the nested `claude -p` call and exits immediately if that variable is already set. Without it the nested call would fire the same hook again.

Every call appends one line to `~/.codex-bridge/at_route.log`: UTC timestamp, alias, exit code, seconds.

## Install

Add the hook to `~/.claude/settings.json` under `hooks.UserPromptSubmit`. Put it after any hooks that must see every prompt, because an exit 2 from this hook stops later hooks too.

```json
{
  "type": "command",
  "command": "bash /Users/domattioli/Projects/agents_Inc/skills/codex-bridge/scripts/at_route.sh",
  "timeout": 130
}
```

Requirements: `jq`, `perl` (for the portable 120-second timeout), the `claude` CLI on PATH. Codex aliases also need the bridge daemon running: `skills/codex-bridge/scripts/up.sh --workdir <an existing directory>`.

Environment overrides:

| Variable | Default | Effect |
|---|---|---|
| `AT_ROUTE_MODE` | `block` | `relay` makes single `@` behave like `@@` |
| `AT_ROUTE_TIMEOUT` | `120` | Seconds before the delegate call is killed |
| `AT_ROUTE_LOG` | `~/.codex-bridge/at_route.log` | Log path |

## Known limits

- A side question leaves no trace in the session. If you want the session model to build on the answer, ask with `@@` or paste the answer in.
- The daemon's `--workdir` must exist. If it is deleted, every Codex alias fails with a misleading `codex CLI not found on PATH` error from `bridge.py`. Restart the daemon from a stable directory.
- A delegate can refuse. Haiku declined a joke prompt during testing. The refusal is shown to you like any other answer.
- Gemini, Mistral and OpenRouter aliases are not wired yet. The bridge has `gask.sh`, `mask.sh` and `oask.sh`, so adding them is a small change in the alias table.

## Prior art

Survey of similar tools and what is new here: [AT-ROUTE-PRIOR-ART.md](AT-ROUTE-PRIOR-ART.md). Short version: Claude Code hooks that pick a model per session or per subagent exist, and `auto-model-router` uses a `#model=` prompt tag, but none blocks the prompt and answers from the hook. The `@` versus `@@` split and the shared Claude plus Codex alias table appear to be new.
