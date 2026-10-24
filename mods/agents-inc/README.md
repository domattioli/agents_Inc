# agents-inc mod

A Claude Code mod that shows an agents-inc delegate working, live, in a subagent transcript (spec 027).

## What it adds

- Agent `agents-inc:relay` (haiku, 3 turns). It calls the tool once and returns the tool text unchanged.
- Tool `mcp__agents-inc__run` with inputs `model`, `slots` and optional `effort`. It runs `agents-inc dispatch`, follows the run's `events.jsonl` with `agents-inc events follow`, and appends each batch of rows to the relay transcript as a notice.
- The tool result is the delegate's `stdout.md` plus the verdict line, the same report a plain dispatch gives.

## Install

`agents-inc install` and `agents-inc repair` do this when `claude` is on PATH and the plugin is absent:

```
claude plugin marketplace add <release>/mods/agents-inc
claude plugin install agents-inc@agents-inc-local
```

- `--no-mod` skips both steps.
- A failure prints `warning: mod install failed (<code>)`. The install stays green.
- `agents-inc uninstall` runs `claude plugin uninstall agents-inc@agents-inc-local` and `claude plugin marketplace remove agents-inc-local`.
- `agents-inc doctor` prints the warning `MOD_NOT_INSTALLED` when the mod is missing. It still reports `READY`.

Manual fallback, from a checkout: run the two commands above with `mods/agents-inc` as the path. To try the mod without installing it: `claude --plugin-dir mods/agents-inc`.

## Permission

Allow the tool, or the relay asks on every run:

```
mcp__agents-inc__run
```

## Use

Start a relay with the Agent tool: `subagent_type: "agents-inc:relay"`, with the model and the slots file path in the prompt. The tool refuses these calls:

- not made through a subagent (no `agentId`);
- free models (gemini, mistral, openrouter): use `agent.sh` for those;
- a model outside `fable opus sonnet haiku astra sol terra luna`;
- a slots path that is not inside the session directory.

Rows are capped at 600 notices per call. Later rows are held back, and one notice per 60 s says how many; the full log stays in `<run dir>/events.jsonl`.

## Stop a run

Stopping the relay aborts the tool call, and the mod runs `agents-inc dispatch --cancel <run dir>`. You can run that command yourself. It acts only while the run has no final outcome and the recorded process group leader is still the process dispatch started. Otherwise it prints `nothing to cancel`.

## Checks

```
claude plugin validate mods/agents-inc
claude plugin test mods/agents-inc
```
