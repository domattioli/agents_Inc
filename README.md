# agents_for_dummies

agents, all the way down

Delegation to cheap AI models, with the discipline to know whether to believe what comes back. Aimed at people who do not code.

**Status: pre-MVP.** The plan is in [`docs/PLAN-MVP.md`](docs/PLAN-MVP.md); most of what it describes is not built yet. What exists today is the delegation mechanism, the supervision discipline, and the docs.

## Docs

| file | reader |
|---|---|
| [`docs/START-HERE.md`](docs/START-HERE.md) | new human, plain language |
| [`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md) | operator/agent, caveman ultra |
| [`docs/EXTENDING.md`](docs/EXTENDING.md) | adding a vendor, model, task class, or domain |
| [`docs/PLAN-MVP.md`](docs/PLAN-MVP.md) | the build plan — cut line, architecture, phases |
| [`skills/workerbee/SKILL.md`](skills/workerbee/SKILL.md) | full supervision discipline |

Two halves, deliberately separate: `skills/codex-bridge/` is mechanism (transport, routing, retries, cost logging), `skills/workerbee/` is judgment (tier choice, trust, verification). No code in the second, no opinions in the first.

## The one rule

An AI model will tell you it succeeded when it did not — not by lying, but by reporting what it meant to produce rather than what it produced. So **the thing that checks the work must not be the thing that did the work.** When a delegate says its gate passed, re-run the check yourself.

Everything else here is downstream of that.

## Quick start

```bash
# one job, wait for it, print the answer
skills/codex-bridge/scripts/agent.sh submit --backend codex --wait "your prompt"

# watch a running job in another pane
skills/codex-bridge/scripts/watch.sh <logfile>

# poll a job's state without reading its output
skills/codex-bridge/scripts/poll.sh --once --pid-match <pat> --log <log> --out <out>
```

Keys live in a file, never on a command line and never in a prompt to a model.

## The HTTP bridge

`bridge.py` exposes the local `codex` CLI over authenticated HTTP, for driving it from another device. It is peripheral to the MVP and the plan defers it — a fresh CLI job per task avoids the daemon lifecycle and session-contamination problems. Kept because it works.

<details>
<summary>Bridge API reference</summary>

### Run

```bash
export CODEX_BRIDGE_TOKEN=$(openssl rand -hex 32)
python3 bridge.py --port 8787
```

`--workdir DIR` sets the working directory for codex execution (default: cwd). It need not be a git repository — the bridge always passes `--skip-git-repo-check`.

### Persistent sessions

The bridge maintains one codex thread across requests, so context carries between prompts. Each prompt reuses the current thread (tracked by `thread_id`); send `"reset": true` to start a new session.

### Endpoints

`GET /health` — no auth.
```bash
curl http://127.0.0.1:8787/health          # {"status":"ok"}
```

`GET /session` — current thread id. `null` means the next prompt starts fresh.
```bash
curl -H "X-Auth-Token: $CODEX_BRIDGE_TOKEN" http://127.0.0.1:8787/session
```

`POST /reset` — clear the session.

`POST /prompt` — execute a prompt via `codex exec`.
```bash
curl -X POST http://127.0.0.1:8787/prompt \
  -H "X-Auth-Token: $CODEX_BRIDGE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"explain currying in Haskell","model":"gpt-5-codex"}'
```
Body: `prompt` (required string), `model` (optional, overrides `--model`), `reset` (optional bool).
Success returns `response`, `thread_id`, and `usage` when available.

### Status codes

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 401 | `X-Auth-Token` missing or wrong |
| 400 | Invalid JSON, missing/non-string `prompt`, non-boolean `reset`, bad `Content-Length` |
| 413 | Body exceeds 1 MiB |
| 500 | codex CLI not on PATH, or unhandled exception |
| 502 | codex exited non-zero; includes stderr tail. A failed `resume` retries once as fresh |
| 504 | codex exceeded `--timeout` |

### Exposing it

ngrok (`ngrok http 8787`; free URLs rotate every 2h), cloudflared (`cloudflared tunnel --url http://localhost:8787`), or Tailscale. Prefer `tailscale serve 8787` (tailnet-only) over `tailscale funnel 8787` (public).

### Security

The token is the only gate, and it grants shell access through codex — protect it like a private key. Generate with `openssl rand -hex 32`, rotate regularly, keep it out of shell history, and bind to `127.0.0.1` (the default).

</details>

## Requirements

Python 3.9+, and the `codex` CLI installed and logged in on PATH.
