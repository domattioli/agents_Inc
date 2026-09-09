# agents_Inc

Pool free model capacity with existing Claude and Codex subscriptions to increase accepted work per dollar without lowering the verification standard.

![Status: pre-MVP / WIP](https://img.shields.io/badge/status-pre--MVP%20%2F%20WIP-orange)
[![Tests](https://github.com/domattioli/agents_Inc/actions/workflows/tests.yml/badge.svg)](https://github.com/domattioli/agents_Inc/actions/workflows/tests.yml)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
[![Contributions welcome](https://img.shields.io/badge/contributions-welcome-blue)](https://github.com/domattioli/agents_Inc/issues)
[![Open issues](https://img.shields.io/github/issues/domattioli/agents_Inc)](https://github.com/domattioli/agents_Inc/issues)
![DOI](https://img.shields.io/badge/DOI-pending-lightgrey)

**How to use:** `PYTHONPATH=. python3 tools/governance_demo.py --fake` — exercises governed routing, policy checks, and ledger recording with no provider keys required; see [Getting started](#getting-started) for real-provider setup.

1. [Why pool model capacity](#1-why-pool-model-capacity)
2. [Asking for work in plain language](#2-asking-for-work-in-plain-language)
3. [How the speckit pipeline and grilling are adapted here](#3-how-the-speckit-pipeline-and-grilling-are-adapted-here)
4. [How the governed pool works](#4-how-the-governed-pool-works)
5. [Project status](#5-project-status)
6. [Where it fits](#6-where-it-fits)
7. [Limitations](#7-limitations)
8. [Future work](#8-future-work)
9. [Getting started](#9-getting-started)
10. [Appendix: HTTP bridge](#10-appendix-http-bridge)

## 1. Why pool model capacity

Delegated work can look successful while being wrong. In this project's own build history, two defects (a wrong `resume` argument order, a missing `--skip-git-repo-check`) passed a subagent's own smoke tests and were only caught when a supervisor read the code directly ([specs/001-codex-delegation-regime/tasks.md](specs/001-codex-delegation-regime/tasks.md)).

`agents_Inc` pools free Gemini, Mistral, and OpenRouter capacity with already-paid Claude and Codex subscriptions. The goal is more accepted work per dollar. Cheap models handle eligible routine work. Costlier models supervise, review, and take over only when evidence justifies escalation.

An accepted task must pass independent checks. Savings and accuracy have not yet been measured, so the project does not claim a savings percentage or quality improvement ([docs/PLAN-MVP.md](docs/PLAN-MVP.md)).

Formerly `agents_for_dummies`. The repository was renamed on 2026-09-07 without rewriting its history.

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 2. Asking for work in plain language

You don't hand-pick every model or write JSON. Name two rungs in plain English; the rest fills in.

### Worked example: name two, get four

The ladder has four rungs — Executive, Orchestrator (a.k.a. Supervisor), Workhorse, Grunt — each a Claude/Codex model pair ([docs/governance/ROUTING-RANKING.md](docs/governance/ROUTING-RANKING.md)). You typically only need to name the top two:

> "Use Fable 5 as Executive and Opus 5 as Orchestrator for this refactor."

That's enough. Executive owns final say and irreversible calls; Orchestrator decomposes and dispatches. Workhorse and Grunt — the models that do the actual coding, research, and classification — derive from the same rung table, no need to name them by hand.

### Layering on constraints

Real dispatch prompts add more than a model name. The full list is 14 required elements (`CLAUDE.md` "Delegation prompt contract"; enforced under the hood by [skills/workerbee/SKILL.md](skills/workerbee/SKILL.md) Step 11) — you don't type all 14 yourself, but three show up often enough to know by name:

- **Success gate / failure gate**, stated separately — what "done" looks like and what counts as a miss, so a delegate's own PASS claim isn't the final word.
- **Effort level** — `low|medium|high|xhigh|max` (Claude) or the same plus `ultra` (Codex), defaulting to medium if you don't name one.
- **Scope boilerplate** — repo-scoped writes only, no commit/push, no credential or cross-repo writes; commit/push authority stays with the run root.

Add whichever of these you care about; the rest of the contract's elements are filled in automatically. See `CLAUDE.md` and `skills/workerbee/SKILL.md` Step 11 for the complete, current list.

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 3. How the speckit pipeline and grilling are adapted here

**Speckit pipeline.** `skills/speckit-pipeline/` is a deliberate, explicit fork of DomI's upstream `speckit-pipeline` v1.5 (from `DomI@476e141`, PR domattioli/DomI#466, unmerged at fork time) — normally this repo's own rule is "never vendor a DomI skill into a consumer tree," and this is a named, logged exception (`docs/DECISIONS.md` D35). Reason: PR #466 shipped a new default dispatch mode with no test coverage; forking let it get fleshed out and proven against this repo's real `docs/governance/ROUTING-RANKING.md` before that risk reached every DomI consumer. Once proven out, the plan is to relay changes upstream to PR #466 and delete this repo's copy (D35 exit criteria).

What got built on top of the fork (D35 addendum, D36): each pipeline phase now resolves its rung name live against `docs/governance/ROUTING-RANKING.md`'s table (`skills/speckit-pipeline/scripts/resolve_rung.py`, fails closed on an unrecognized rung rather than guessing) and records dispatch/return into the append-only ledger (`ledger_bridge.py`) — a passive recorder bolted onto phases that still run unchanged via the `Agent` tool, not a new execution engine. Building this also caught a real bug: the ledger's SQLite schema silently dropped rows tagged with D27 rung names because of a stale `CHECK` constraint — fixed in the bridge's rung-to-schema-tier mapping.

**Grilling.** There's no packaged `grill-me`/`grill-with-docs` skill in this repo. "Grilling" here means the CEO-led interrogation sessions that produce binding rulings in `docs/DECISIONS.md` (e.g. the 2026-09-06 grill session with fable/astra that produced D27's rung ladder, and the 2026-09-07 session behind D35/D36) — plus element 4 of the delegation prompt contract, the "grill clause," which requires every dispatch prompt to surface gaps and ambiguity rather than have the delegate guess. Grilling is a decision-making discipline and a prompt-contract requirement in this repo, not a standalone invocable skill.

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 4. How the governed pool works

Routing uses four rungs: Grunt, Workhorse, Orchestrator, and Executive. Each rung names one Claude model and one Codex model. Gemini, Mistral, and OpenRouter can enter only at Grunt, and only for `extract` and `summarize` tasks. `workerbees/router.py` enforces that boundary and selects the vendor and model for each dispatch ([workerbees/routing.json](workerbees/routing.json), [workerbees/router.py](workerbees/router.py)).

Moving to a costlier rung requires a recorded reason: repeated failed checks or a provider quota pause. Worker confidence is not an escalation reason.

Verification runs in this order:

1. `workerbees/verifier.py` checks cited claims against source text without calling a model.
2. `workerbees/reviewer.py` performs semantic review using a different provider. It returns `same_vendor` without making a model call when reviewer and worker providers match.
3. `workerbees/ledger.py` records dispatches, returns, reviews, and acceptance decisions in an append-only audit trail, dual-written by default to JSONL and SQLite.

A worker's own PASS or FAIL is never the final verdict. Acceptance follows verifier and reviewer results recorded in the ledger ([workerbees/pipeline.py](workerbees/pipeline.py)).

Today's schema still requires a Claude model name and a Codex model name at every tier; allowing either subscription to be optional is a goal of the pooling design, not current behavior ([workerbees/config_schema.py](workerbees/config_schema.py), [workerbees/keys.py](workerbees/keys.py)).

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 5. Project status

**Pre-MVP and under active development.** The build plan and cut line live in [docs/PLAN-MVP.md](docs/PLAN-MVP.md).

Built and tested today:

- The four-rung router and optional-provider restrictions.
- Deterministic citation verification and enforced cross-vendor semantic review.
- An append-only JSONL and SQLite ledger.
- A local SHA-256 content-addressed artifact store.
- The governed dispatch gateway, including envelope, policy, registry, and budget checks.
- The live `agent.sh`/`agent_runner.py` dispatch path (shells out to the Codex CLI directly; `bridge.py` is a separate HTTP path for a second device, see appendix).
- 462 automated tests passing locally with `python3 -m unittest discover -s tests`.

`WORKERBEES_GOVERNANCE` still defaults to `off`. The governed path therefore exists but is not enabled by default ([workerbees/gateway.py](workerbees/gateway.py)).

The `gask.sh`, `mask.sh`, and `oask.sh` scripts are the free-tier legacy path. They still work when governance is off, are refused in governed lanes, and are planned to be folded into the governed dispatcher.

Bindle Backend A is built: the local content-addressed artifact store captures and retrieves run output, and `WORKERBEES_ARTIFACTS` defaults to `local`. Backend B remains deferred; it requires an idempotent `finish_run` terminal event and a validated invoice mapping before any real `deislabs/bindle` installation or publication path.

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 6. Where it fits

`agents_Inc` is an integration and governance layer above provider tools. It does not replace their CLIs or instruction formats.

| Provider tool | Used here | Changed | Notes |
|---|---|---|---|
| Claude Skills (SKILL.md format) | Yes | No — standard frontmatter | Packages routing and verification judgment as reusable prose (`skills/workerbee`, `skills/codex-bridge`) |
| Claude subagents / Agent tool | No | — | Single-vendor; cannot enforce cross-vendor review by itself |
| Claude Code hooks | No | — | None configured; a future hook could run tests after edits or guard `routing.json` changes |
| Model Context Protocol (MCP) | No | — | Dispatch uses an HTTP bridge and CLI wrapper |
| OpenAI Codex CLI | Yes | Wrapped | `bridge.py` adds a persistent-thread HTTP session; `agent.sh` and `agent_runner.py` add a governed asynchronous job queue bound to the ledger |
| OpenAI Assistants / Agent SDK | No | — | Uses the Codex CLI and this repository's dispatcher |
| Built here, no vendor equivalent | — | — | `ledger.py` (audit trail), `reviewer.py` (cross-vendor enforcement), `verifier.py` (deterministic pre-check), `artifacts.py` (content-addressed store), `router.py`/`routing.json` (tier and vendor routing) |

This repository is for developers who use more than one model provider, want to control incremental spend, and need delegated work checked independently before acceptance.

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 7. Limitations

The project has not yet measured cost savings or accuracy against its baseline. Local passing tests establish that the implementation behaves as coded, not that it is reliable in production. `WORKERBEES_GOVERNANCE` remains off by default, so the enforced-review path this repository is built around is not the path a fresh checkout runs.

Cross-vendor review catches disagreement between models; it does not catch a shared blind spot both vendors have. Deterministic verification checks what a check can express (citations exist, a file changed, a command exit code) and does not substitute for a human judgment call on scope or design quality. Bindle Backend B (remote artifact publication) is unimplemented, so artifacts stay local-only today.

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 8. Future work

Tracked as open issues on this repo:

- [#7](https://github.com/domattioli/agents_Inc/issues/7) — a CLI-agnostic dispatch mechanism, the inverse of `codex-bridge`, so Codex can drive the same workflow and call Claude models.
- [#8](https://github.com/domattioli/agents_Inc/issues/8) — `astra` dispatch with `--approve-for-me` can hit host-classifier blocks that `terra`/`luna` do not.
- [#6](https://github.com/domattioli/agents_Inc/issues/6) — `codex-bridge`'s `up.sh` hardcodes a stale pre-rename `BASE` path; `--workdir` doesn't override it.
- [#4](https://github.com/domattioli/agents_Inc/issues/4) — a dispatch-prompt style-compression template, with findings and a validation plan.
- [#3](https://github.com/domattioli/agents_Inc/issues/3) — brainstorm: mandate the speckit workflow for Supervisor-rung work.

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 9. Getting started

### Install and configure providers

Run the project from the repository root. Its Python code uses the standard library, so there is no Python package-install step.

1. Install the Claude Code CLI, run `claude`, and log in with an Anthropic subscription.
2. Install the Codex CLI and run `codex login` with a ChatGPT/OpenAI account.
3. Optionally configure free-tier providers:

```bash
python3 -m workerbees.keys gemini
python3 -m workerbees.keys mistral
python3 -m workerbees.keys openrouter
```

Each optional-provider command opens the provider's key page and requests a hidden paste. Press Enter to skip that provider. Stored keys go to `~/.config/workerbees/.env` with mode `0600`; the agent does not receive the raw key.

Never place a key in a command argument or model prompt. Skipping an optional key is not an error. It simply removes that provider from the available pool. Current routing can dispatch optional providers only for Grunt-tier `extract` and `summarize` tasks.

### Quick start

1. Exercise governed routing, policy checks, and ledger recording without provider keys:

```bash
PYTHONPATH=. python3 tools/governance_demo.py --fake
```

The demo runs a fake worker and prints the resulting decision records.

2. After configuring the provider CLIs, submit a real Codex job:

```bash
skills/codex-bridge/scripts/agent.sh submit --backend codex --wait "your prompt"
```

### How it feels to use

**Current behavior**

```bash
skills/codex-bridge/scripts/agent.sh submit --backend codex --wait "your prompt"
```

You receive raw output and decide whether to trust it or invoke the reviewer path manually. Both Claude and Codex logins must exist even when this call uses only Codex.

**Future beta goal — not yet built**

```text
submit task → choose cheapest eligible provider → independent review → verified result + ledger entry
```

The planned interface will work with whichever paid provider is available, use a second paid or free vendor when eligible for review, and remove the manual acceptance step.

### Requirements

- Python 3.9 or later. The test suite also runs on Python 3.14 ([specs/001-codex-delegation-regime/plan.md](specs/001-codex-delegation-regime/plan.md), [specs/002-dispatch-graph-ledger/plan.md](specs/002-dispatch-graph-ledger/plan.md)).
- Bash 3.2 or later. The lifecycle and client scripts support macOS system Bash.
- Claude Code CLI, authenticated through an Anthropic subscription.
- Codex CLI, authenticated through a ChatGPT/OpenAI account.
- Optional: Gemini, Mistral, or OpenRouter API credentials. A missing optional key skips that provider rather than blocking the system.

No LICENSE file exists yet.

### Documentation map

| File | Reader |
|---|---|
| [docs/START-HERE.md](docs/START-HERE.md) | New to the system, plain language |
| [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) | Operator or agent, dense reference |
| [docs/EXTENDING.md](docs/EXTENDING.md) | Adding a vendor, model, task class, or domain |
| [docs/PLAN-MVP.md](docs/PLAN-MVP.md) | Build plan, cut line, architecture, and phases |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Binding rulings, rationale, and evidence |
| [docs/HANDOFF.md](docs/HANDOFF.md) | Continuing the work in a fresh session |
| [skills/workerbee/SKILL.md](skills/workerbee/SKILL.md) | Full supervision discipline |

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 10. Appendix: HTTP bridge

`bridge.py` exposes the local `codex` CLI over authenticated HTTP for a second device. It is peripheral to the MVP and uses one serialized Codex thread across requests ([bridge.py](bridge.py)).

<details>
<summary>Bridge API reference</summary>

### Run

```bash
export CODEX_BRIDGE_TOKEN=$(openssl rand -hex 32)
python3 bridge.py --port 8787
```

`--workdir DIR` sets the Codex working directory; the default is the current directory. The directory need not be a Git repository because the bridge passes `--skip-git-repo-check`. The default bind address is `127.0.0.1`, the default execution timeout is 60 seconds, and the default Codex sandbox is `workspace-write`.

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

The request body accepts `prompt` (required string), `model` (optional), and `reset` (optional boolean). A successful response contains `response`, `thread_id`, `usage`, and session-restart metadata where applicable.

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

The bearer token is the bridge's authentication gate. Successful requests can direct a Codex process in the configured working directory and sandbox. Protect the token as a secret, rotate it when exposed, and retain the default `127.0.0.1` binding unless an authenticated network layer is in place.

</details>

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>
