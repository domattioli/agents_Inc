# agents_for_dummies

agents, all the way down

## Project

- Delegation system
  - **Purpose**
    - It sends narrow jobs to cheap AI models and checks the returned work.
  - **Audience**
    - It is aimed at people who do not code.
  - **Status**
    - **Pre-MVP.** The plan is in [`docs/PLAN-MVP.md`](docs/PLAN-MVP.md), and most of it is not built yet.
    - The delegation mechanism, supervision discipline, and documentation exist today.

## Documentation

| file | reader |
|---|---|
| [`docs/START-HERE.md`](docs/START-HERE.md) | new human, plain language |
| [`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md) | operator/agent, caveman ultra |
| [`docs/EXTENDING.md`](docs/EXTENDING.md) | adding a vendor, model, task class, or domain |
| [`docs/PLAN-MVP.md`](docs/PLAN-MVP.md) | the build plan: cut line, architecture, phases |
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | picking this up in a fresh session |
| [`skills/workerbee/SKILL.md`](skills/workerbee/SKILL.md) | full supervision discipline |

## Two halves

- System design
  - **Mechanism**
    - `skills/codex-bridge/` owns transport, routing, retries, and cost logging.
  - **Judgment**
    - `skills/workerbee/` owns tier choice, trust, and verification.
  - **Boundary**
    - The mechanism contains no judgment, and the judgment layer contains no code.

## Verification rule

- Independent checking
  - **Failure mode**
    - An AI model can report what it meant to produce instead of what it produced.
  - **Rule**
    - The thing that checks the work must not be the thing that did the work.
  - **Practice**
    - Re-run the check yourself when a delegate says its gate passed.
  - **Reason**
    - The check separates useful delegation from dangerous delegation.
  - **Scope**
    - Every other design choice follows this rule.

## Quick start

```bash
# one job, wait for it, print the answer
skills/codex-bridge/scripts/agent.sh submit --backend codex --wait "your prompt"

# watch a running job in another pane
skills/codex-bridge/scripts/watch.sh <logfile>

# poll a job's state without reading its output
skills/codex-bridge/scripts/poll.sh --once --pid-match <pat> --log <log> --out <out>
```

- Key handling
  - **Location**
    - Keys live in a file.
  - **Prohibition**
    - Keys never belong on a command line or in a model prompt.

## HTTP bridge

- `bridge.py`
  - **Function**
    - It exposes the local `codex` CLI over authenticated HTTP for another device.
  - **MVP status**
    - It is peripheral to the MVP because a fresh CLI job per task avoids daemon lifecycle and session-contamination problems.
  - **Availability**
    - It remains because it works.

<details>
<summary>Bridge API reference</summary>

### Run

```bash
export CODEX_BRIDGE_TOKEN=$(openssl rand -hex 32)
python3 bridge.py --port 8787
```

`--workdir DIR` sets the working directory for codex execution (default: cwd). It need not be a git repository. The bridge always passes `--skip-git-repo-check`.

### Persistent sessions

The bridge maintains one codex thread across requests, so context carries between prompts. Each prompt reuses the current thread, tracked by `thread_id`. Send `"reset": true` to start a new session.

### Endpoints

`GET /health`: no auth.
```bash
curl http://127.0.0.1:8787/health          # {"status":"ok"}
```

`GET /session`: current thread id. `null` means the next prompt starts fresh.
```bash
curl -H "X-Auth-Token: $CODEX_BRIDGE_TOKEN" http://127.0.0.1:8787/session
```

`POST /reset`: clear the session.

`POST /prompt`: execute a prompt via `codex exec`.
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
| 502 | codex exited non-zero. Includes stderr tail. A failed `resume` retries once as fresh |
| 504 | codex exceeded `--timeout` |

### Exposing it

Use ngrok (`ngrok http 8787`), whose free URLs rotate every 2h, cloudflared (`cloudflared tunnel --url http://localhost:8787`), or Tailscale. Prefer `tailscale serve 8787` (tailnet-only) over `tailscale funnel 8787` (public).

### Security

The token is the only gate, and it grants shell access through codex. Protect it like a private key. Generate with `openssl rand -hex 32`, rotate regularly, keep it out of shell history, and bind to `127.0.0.1` (the default).

</details>

## Requirements

- Runtime
  - **Python**
    - Python 3.9+ is required.
  - **CLI**
    - The `codex` CLI must be installed and logged in on PATH.
