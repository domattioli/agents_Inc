# agents_Inc

**Pool free Gemini, Mistral, and OpenRouter capacity with already-paid Claude and Codex subscriptions in one governed delegation pipeline. The objective is more accepted work per dollar, without accepting lower-quality work as a cost-saving measure.**

An accepted task is one that passes the required verification and review gates. The project defines cost as dollars per accepted task against an all-frontier baseline, with seeded faults as the quality floor. Savings and quality outcomes have not yet been measured; [`docs/PLAN-MVP.md`](docs/PLAN-MVP.md) explicitly prohibits reporting a savings percentage before both target workflows are measured.

Formerly `agents_for_dummies`. Renamed 2026-09-07; the repository history is unchanged.

## Pool capacity before buying more

The routing system separates routine work from expensive supervision:

- The four-rung ladder—Grunt, Workhorse, Orchestrator, and Executive—pairs a Claude model with a Codex model at each rung. [`docs/governance/ROUTING-RANKING.md`](docs/governance/ROUTING-RANKING.md) is the table of record.
- Claude and Codex are the required providers. Gemini, Mistral, and OpenRouter are optional capacity sources (`workerbees/routing.json`).
- In the current router, optional providers appear only at the Grunt tier and are permitted only for `extract` and `summarize`. This boundary is enforced by `workerbees/router.py`, not merely documented as policy.
- The broader budget modality keeps ladder models for supervision, orchestration, review, and fallback while assigning eligible routine work to free grunts. Free-grunt review must come from a different upstream vendor (`docs/DECISIONS.md` D27 and `CONTEXT.md`). The current router implements only the narrower optional-provider path described above.

Promotion to a more expensive rung requires a recorded gate reason, repeated failed checks, or a provider quota pause. Worker confidence alone is not a promotion reason (`CLAUDE.md`, `docs/DECISIONS.md` D27).

## What makes the pool trustworthy

Cheap capacity is useful only if its output can be accepted on evidence rather than self-report.

- **Deterministic verification.** `workerbees/verifier.py` checks source-bound claims before semantic review.
- **Cross-vendor review.** `workerbees/reviewer.py` excludes the worker’s provider when selecting a reviewer and returns `same_vendor` without making a model call if a caller supplies a same-provider route.
- **Audit ledger.** `workerbees/ledger.py` records dispatch and return events, lineage, review relationships, gate reasons, and cost rollups. Storage is selectable as JSONL, normalized SQLite, or both through `WORKERBEES_STORE`; the default is `both`.
- **Artifact binding.** `workerbees/artifacts.py` stores deliverables by SHA-256 so a review can remain tied to the exact bytes examined. The ledger owns what happened; the artifact store owns what was produced. Local artifact storage is enabled by default through `WORKERBEES_ARTIFACTS=local`, with manual retention and purge rules documented in `docs/DECISIONS.md` D37/D38.

The mechanism does not treat a worker’s PASS or FAIL as the final verdict. Acceptance follows verifier and reviewer results (`CONTEXT.md`, `workerbees/pipeline.py`).

## Relationship to vendor-native tooling

This project is positioned as an integration layer above vendor-native orchestration tools, not as a competing subagent framework. Claude subagents, skills, hooks, and Agent SDK components—and the corresponding OpenAI tools—can remain the execution primitives. `agents_Inc` adds routing across provider boundaries, pools third-party free capacity with subscription-backed models, and enforces reviewer independence at the provider boundary. That differentiation is architectural reasoning based on `workerbees/routing.json` and `workerbees/reviewer.py`, not a measured comparison with vendor-native products.

## Status

**Pre-MVP and under active development.** The build plan and cut line live in [`docs/PLAN-MVP.md`](docs/PLAN-MVP.md).

The work is moving toward more deterministic routing, acceptance, budgeting, and recovery, together with human-factors usability: guided setup, explicit and resumable human intervention, bounded receipts, and clear separation between verified output and decisions that still require a person. These are plan targets, not completed usability or performance claims (`docs/PLAN-MVP.md`).

Implemented and tested today:

- The delegation mechanism, routing ladder, and supervision discipline (`skills/workerbee/`, `workerbees/`).
- The governed dispatch gateway with envelope, policy, registry, and budget checks in `off`, `shadow`, or `enforce` mode. `WORKERBEES_GOVERNANCE` still defaults to `off`, so the governed path is not exercised by default (`workerbees/gateway.py`, `docs/DECISIONS.md` D37).
- The local content-addressed artifact store, enabled by default with `WORKERBEES_ARTIFACTS=local` (`workerbees/artifacts.py`, `docs/DECISIONS.md` D38).
- 462 automated tests, passing (`python3 -m unittest discover -s tests`; recorded in `docs/DECISIONS.md` D38).

Not yet built are the Bindle registry and distribution backend, signing, and most later phases in [`docs/PLAN-MVP.md`](docs/PLAN-MVP.md). Measured savings and accuracy results are also pending. This README distinguishes implemented behavior from planned behavior.

## Two halves

| Layer | Owns | Contains |
|---|---|---|
| **Mechanism** (`skills/codex-bridge/`, `workerbees/gateway.py`, `workerbees/router.py`) | Transport, retries, cost logging, model selection | Code, no judgment |
| **Judgment** (`skills/workerbee/`) | Tier choice, trust, verification discipline | Prose instructions, no transport code |

The split permits transport changes without rewriting the supervision rules, and supervision changes without replacing the transport layer.

## Who this is for

This repository is for developers combining Claude, Codex, Gemini, Mistral, or OpenRouter capacity who need to control incremental model spend and verify delegated work independently. The relevant implementation is inspectable in `workerbees/router.py`, `workerbees/policy.py`, `workerbees/reviewer.py`, `workerbees/ledger.py`, and `skills/workerbee/SKILL.md`.

## Documentation

| File | Reader |
|---|---|
| [`docs/START-HERE.md`](docs/START-HERE.md) | New to the system, plain language |
| [`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md) | Operator or agent, dense reference |
| [`docs/EXTENDING.md`](docs/EXTENDING.md) | Adding a vendor, model, task class, or domain |
| [`docs/PLAN-MVP.md`](docs/PLAN-MVP.md) | Build plan, cut line, architecture, and phases |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Binding rulings, rationale, and evidence |
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | Continuing the work in a fresh session |
| [`skills/workerbee/SKILL.md`](skills/workerbee/SKILL.md) | Full supervision discipline |

## Quick start

```bash
# submit one Codex job, wait for it, and print the answer
skills/codex-bridge/scripts/agent.sh submit --backend codex --wait "your prompt"

# watch a running job in another pane
skills/codex-bridge/scripts/watch.sh <logfile>

# poll a job's state without reading its output
skills/codex-bridge/scripts/poll.sh --once --pid-match <pat> --log <log> --out <out>
```

Provider credentials belong in credential files, not command arguments or model prompts. See the scripts under `skills/codex-bridge/scripts/` for the supported provider paths.

## HTTP bridge

`bridge.py` exposes the local `codex` CLI over authenticated HTTP for a second device. It is peripheral to the MVP and uses one serialized Codex thread across requests (`bridge.py`).

<details>
<summary>Bridge API reference</summary>

### Run

```bash
export CODEX_BRIDGE_TOKEN=$(openssl rand -hex 32)
python3 bridge.py --port 8787
```

`--workdir DIR` sets the Codex working directory; the default is the current directory. The directory need not be a Git repository because the bridge passes `--skip-git-repo-check`. The default bind address is `127.0.0.1`, the default execution timeout is 60 seconds, and the default Codex sandbox is `workspace-write` (`bridge.py`).

### Persistent sessions

The bridge maintains one Codex thread across requests. Each prompt reuses the current `thread_id`; send `"reset": true` with a prompt or call `POST /reset` to start a new thread.

### Endpoints

`GET /health` requires no authentication.

```bash
curl http://127.0.0.1:8787/health
# {"status":"ok"}
```

`GET /session` returns the current thread and sandbox. A null `thread_id` means the next prompt starts a new thread.

```bash
curl \
  -H "X-Auth-Token: $CODEX_BRIDGE_TOKEN" \
  http://127.0.0.1:8787/session
```

`POST /reset` clears the current thread.

```bash
curl -X POST \
  -H "X-Auth-Token: $CODEX_BRIDGE_TOKEN" \
  http://127.0.0.1:8787/reset
```

`POST /prompt` executes a prompt through `codex exec`.

```bash
curl -X POST http://127.0.0.1:8787/prompt \
  -H "X-Auth-Token: $CODEX_BRIDGE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"explain currying in Haskell","model":"gpt-5-codex"}'
```

The request body accepts `prompt` (required string), `model` (optional), and `reset` (optional boolean). A successful response contains `response`, `thread_id`, `usage`, and session-restart metadata where applicable (`bridge.py`).

### Status codes

| Status | Meaning |
|---|---|
| 200 | Success |
| 400 | Invalid request body or fields |
| 401 | Missing or incorrect `X-Auth-Token` |
| 404 | Unknown endpoint |
| 413 | Request body exceeds 1 MiB |
| 429 | Codex reported a rate or quota limit |
| 500 | Codex CLI unavailable or an unhandled bridge error |
| 502 | Codex exited unsuccessfully; a failed session resume is retried once as a fresh thread unless rate-limited |
| 504 | Codex exceeded the configured timeout |

### Exposing it

A private network or authenticated tunnel can carry the bridge to another device. Tailscale Serve, cloudflared, and ngrok are possible transports; their installation and security properties are outside this repository.

### Security

The bearer token is the bridge’s authentication gate, and successful requests can direct a Codex process in the configured working directory and sandbox. Protect the token as a secret, rotate it when exposed, and retain the default `127.0.0.1` binding unless an authenticated network layer is in place (`bridge.py`).

</details>

## Requirements

- Python 3.9 or later (`specs/001-codex-delegation-regime/plan.md`).
- Claude Code and Codex CLIs installed and authenticated for the required providers (`workerbees/routing.json`, `CONTEXT.md`).
- Optional Gemini, Mistral, or OpenRouter credentials when using those free-tier routes. Missing optional credentials skip those providers; confidential inputs require explicit workspace authorization (`CONTEXT.md`, `workerbees/router.py`).
