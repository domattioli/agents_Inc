# agents_Inc

**A governed delegation system for agentic AI work: route tasks to the cheapest model that can do the job, verify every result independently, and keep an auditable record of what happened.**

Formerly `agents_for_dummies`. Renamed 2026-09-07 — same repo, same history.

## The problem

Multi-model agentic pipelines fail in a specific, recurring way: a delegated model reports success on work it did not actually complete correctly, and the report is convincing. This was observed directly during this project's own build sessions — the same failure, three times in a row, each time self-reported as passing. The fix is not a better prompt. It is a structural rule: **the thing that checks the work must never be the thing that did the work.**

Everything in this repo follows from that one constraint.

## What it is

A working implementation, not a framework pitch. Concretely, this repo gives an agentic AI developer four things:

1. **A cost-aware routing ladder.** Four rungs — Grunt, Workhorse, Orchestrator, Executive — each pinned to a Claude/Codex model pair (`docs/governance/ROUTING-RANKING.md` is the table of record). Routine work defaults to free or cheap models; escalation to an expensive model requires a recorded reason, never mere confidence. Free-tier grunts (Gemini, Mistral, OpenRouter) never touch a paid Codex call — that boundary is enforced in code, not just policy.
2. **An independent verification layer.** The model that produced a draft is never the model that checks it. Reviews cross vendors by default (`workerbees/reviewer.py`); a deterministic verifier checks citations against source text before any AI reviewer runs at all (`workerbees/verifier.py`). A worker's own PASS/FAIL is data, not a verdict.
3. **An append-only audit ledger.** Every dispatch, return, review, correction, and promotion is recorded to a dual-write store (JSONL + normalized SQLite) with lineage, cost rollup, and lint checks for governance violations (e.g. an unreviewable escalation, or a same-vendor "independent" review). Nothing here is self-graded — a claim of correctness is checked against the ledger, not taken on the model's word.
4. **A content-addressed artifact store.** Deliverables are hashed and stored (`workerbees/artifacts.py`), so a review edge that cites "the exact draft I checked" can be re-verified byte-for-byte later, not just trusted. Sibling to the ledger, not a replacement for it: the ledger owns *what happened*, the artifact store owns *what was produced*. Manual retention (no silent auto-delete of confidential drafts) — see `docs/DECISIONS.md` D37/D38.

None of this requires trusting any single model. That is the actual product: a way to spend less on AI work while trusting the output more, with a paper trail if something goes wrong.

## Status

**Pre-MVP**, honestly. The build plan and cut line live in [`docs/PLAN-MVP.md`](docs/PLAN-MVP.md). What exists today and is tested:

- The delegation mechanism, the routing ladder, and the verification discipline (`skills/workerbee/`, `workerbees/`).
- The governed dispatch gateway with envelope/policy/registry checks, in shadow or enforce mode (`WORKERBEES_GOVERNANCE`, default `off` — the surrounding machinery is real but not yet exercised by default; see `docs/DECISIONS.md` D37 for the honest read on that gap).
- The content-addressed artifact store (`WORKERBEES_ARTIFACTS`, default `local` as of D38).
- 462 automated tests, passing (`python3 -m unittest discover -s tests`).

What is not built: the Bindle registry/distribution backend, signing, and most of `docs/PLAN-MVP.md`'s later phases. This README describes what runs today, not the roadmap.

## Two halves

| Layer | Owns | Contains |
|---|---|---|
| **Mechanism** (`skills/codex-bridge/`, `workerbees/gateway.py`, `workerbees/router.py`) | Transport, retries, cost logging, model selection | Code, no judgment |
| **Judgment** (`skills/workerbee/`) | Tier choice, trust, verification discipline | Prose (a skill definition), no code |

The split is deliberate: swap the transport layer without touching the supervision rules that make delegation safe, and vice versa.

## Who this is for

If you're wiring Claude, Codex, Gemini, or Mistral into an agentic pipeline and either (a) your API bill is a real cost or (b) you've been burned by a model that reported success on broken work — this is a reference implementation of the guardrails, not a toy demo. Read the code; the discipline is in `workerbees/policy.py`, `workerbees/ledger.py`, and `skills/workerbee/SKILL.md`, and none of it is hidden behind an abstraction you can't inspect.

## Documentation

| File | Reader |
|---|---|
| [`docs/START-HERE.md`](docs/START-HERE.md) | New to the system, plain language |
| [`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md) | Operator/agent, dense reference |
| [`docs/EXTENDING.md`](docs/EXTENDING.md) | Adding a vendor, model, task class, or domain |
| [`docs/PLAN-MVP.md`](docs/PLAN-MVP.md) | Build plan: cut line, architecture, phases |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Every binding ruling, with rationale and evidence |
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | Picking this up in a fresh session |
| [`skills/workerbee/SKILL.md`](skills/workerbee/SKILL.md) | Full supervision discipline |

## Quick start

```bash
# one job, wait for it, print the answer
skills/codex-bridge/scripts/agent.sh submit --backend codex --wait "your prompt"

# watch a running job in another pane
skills/codex-bridge/scripts/watch.sh <logfile>

# poll a job's state without reading its output
skills/codex-bridge/scripts/poll.sh --once --pid-match <pat> --log <log> --out <out>
```

Keys live in a file, never on a command line or in a model prompt.

## HTTP bridge

`bridge.py` exposes the local `codex` CLI over authenticated HTTP for a second device. It is peripheral to the MVP — a fresh CLI job per task avoids daemon lifecycle and session-contamination problems — but it works, and it stays.

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
|---|---|
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

- Python 3.9+
- The `codex` CLI, installed and logged in on `PATH`
- An Anthropic subscription (Claude models) and/or a ChatGPT subscription (OpenAI models) for the paid rungs; free tiers (Gemini, Mistral, OpenRouter) cover the default budget-mode path
