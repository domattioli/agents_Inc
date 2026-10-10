<p align="center"><img src="https://raw.githubusercontent.com/domattioli/agents_Inc/main/docs/assets/logo-wide.png" width="100%" alt="agents_Inc: a crew of original cartoon monsters at work on a night-shift dispatch floor"></p>

# agents_Inc

<p align="center"><strong>A corporate org chart for AI agents: you ask, the session you talk to dispatches a Lead model, and the Lead runs cheaper Worker models. The aim is more checked work from the AI subscriptions you already pay for.</strong></p>

<p align="center">
<img alt="Status: experimental" src="https://img.shields.io/badge/status-experimental-orange">
<a href="https://github.com/domattioli/agents_Inc/actions/workflows/tests.yml"><img alt="Tests" src="https://github.com/domattioli/agents_Inc/actions/workflows/tests.yml/badge.svg"></a>
<a href="https://pypi.org/project/agents-inc/"><img alt="PyPI" src="https://img.shields.io/pypi/v/agents-inc?cacheSeconds=3600"></a>
<img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue">
<a href="https://github.com/domattioli/agents_Inc/blob/main/LICENSE"><img alt="License: PolyForm Small Business 1.0.0 + no AI training" src="https://img.shields.io/badge/license-PolyForm%20Small%20Business%201.0.0%20%2B%20no%20AI%20training-lightgrey"></a>
<a href="https://github.com/domattioli/agents_Inc/issues"><img alt="Open issues" src="https://img.shields.io/github/issues/domattioli/agents_Inc"></a>
<a href="https://doi.org/10.5281/zenodo.22670100"><img alt="DOI" src="https://zenodo.org/badge/DOI/10.5281/zenodo.22670100.svg"></a>
</p>

## Table of Contents

1. [Status & Roadmap](#1-status--roadmap)
2. [Why it exists](#2-why-it-exists)
3. [Installation](#3-installation)
4. [Quick start](#4-quick-start)
5. [How it works](#5-how-it-works)
6. [Limitations](#6-limitations)
7. [Documentation](#7-documentation)
8. [Citation and license](#8-citation-and-license)

## 1. Status & Roadmap

Version 0.3.1. The project is experimental and pre-MVP. The governed path (`WORKERBEES_GOVERNANCE`) is off by default. Changes per release are in the [CHANGELOG](https://github.com/domattioli/agents_Inc/blob/main/CHANGELOG.md). The build plan and cut line are in [docs/PLAN-MVP.md](https://github.com/domattioli/agents_Inc/blob/main/docs/PLAN-MVP.md). Open work is tracked in [the issues](https://github.com/domattioli/agents_Inc/issues).

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 2. Why it exists

Delegated model work can look done while it is wrong. A flat pool of agents has no way to catch that. `agents_Inc` borrows a [corporate org chart](https://github.com/domattioli/agents_Inc/blob/main/docs/governance/DELEGATION-MODEL.md). The CEO is you. The CoS (chief of staff) is the session you talk to. A Lead manages one run, and a Worker reports to a Lead.

Cheap models take routine work, and costlier models manage. An author never grades its own work: the Lead checks what its Workers report before anything moves up. Savings are not yet measured, so none are claimed ([docs/PLAN-MVP.md](https://github.com/domattioli/agents_Inc/blob/main/docs/PLAN-MVP.md)).

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 3. Installation

Requirements: Python 3.10 or later, Bash 3.2 or later, `jq`, and the Claude Code CLI signed in to an Anthropic subscription. The Codex CLI is optional; when present, it serves the Codex rungs and cross-vendor review.

```bash
pip install agents-inc
agents-inc install     # skills ship in the package; no checkout needed
agents-inc doctor      # first line prints READY when the install works
```

Restart Claude Code (and Codex, if used) after the install. `agents-inc install --without-codex` skips Codex on purpose. To install from a git checkout instead, pass `--source <checkout>`. Optional Gemini, Mistral and OpenRouter keys, the setup decision tree and key storage rules are in [docs/START-HERE.md](https://github.com/domattioli/agents_Inc/blob/main/docs/START-HERE.md).

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 4. Quick start

Name your models in plain English. The ladder decides who manages whom, and the rest fills in. You do not hand-pick every model or write JSON.

Write the request to the CoS as `<task>. <models>.`, for example:

> "Fix the parser. opus, haiku."

The higher rung manages and the lower rung reports to it, so opus is the Lead and haiku is its Worker. Defaults fill the rest: effort medium, gates derived from the task, and the home repo from the consumer's `AGENTS.md`. Each extra word, such as an effort level, overrides one default.

| Rung | Claude | Codex | Role |
|---|---|---|---|
| Executive | fable | astra | Final say, irreversible acts, conflicting results |
| Orchestrator | opus | sol | Decompose, dispatch, plan |
| Workhorse | sonnet | terra | Normal coding, research, synthesis |
| Grunt | haiku | luna | Classify, extract, summarize; free Gemini, Mistral and OpenRouter models enter only here |

The CoS then runs one command. It renders the prompt, lints it, snapshots the tree, launches the delegate and checks the report:

```bash
agents-inc dispatch --slots slots.json --model sonnet --dry-run   # drop --dry-run to launch
agents-inc models chain supervisor=opus                            # change the default REPORTING CHAIN
```

Every dispatch prompt carries a `REPORTING CHAIN` line derived from the ladder, and every launched dispatch writes one `dispatched` row to the ledger. Codex delegates can write to `--cwd` by default, the same as a Claude subagent; the slot `CODEX_WRITE: no` makes one read-only. A worked slots file is in [skills/workerbee/slots.md](https://github.com/domattioli/agents_Inc/blob/main/skills/workerbee/slots.md).

Two more entry points need no dispatch. `PYTHONPATH=. python3 tools/governance_demo.py --fake`, run from a checkout, shows routing, policy checks and ledger records with no provider keys. `@haiku <question>` inside any Claude Code session sends one side question to a cheaper model before the session model runs ([docs/at-route/AT-ROUTE.md](https://github.com/domattioli/agents_Inc/blob/main/docs/at-route/AT-ROUTE.md)).

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 5. How it works

![Delegation and support flow: CEO, CoS, Lead, and Worker roles across the nine speckit phases, with model rungs shown as cost classes](https://raw.githubusercontent.com/domattioli/agents_Inc/main/docs/assets/delegation-model.svg)

- **Routing.** A router picks the vendor and rung for each task from a written policy ([agents_inc/routing.json](https://github.com/domattioli/agents_Inc/blob/main/agents_inc/routing.json)). Rung names are cost classes, not job titles; the reporting chain sets the role.
- **Grilling and speckit.** The CoS grills you one question at a time until the request is sharp, then a speckit pipeline gates it through spec, plan, tasks and review.
- **Verification.** A deterministic verifier checks cited claims with no model call. A reviewer from a different vendor then checks the meaning. A Worker's own PASS never decides acceptance.
- **Ledger.** An append-only JSONL and SQLite ledger records every dispatch, return, review and acceptance decision.
- **Models.** Each Codex alias is pinned to one slug. `agents-inc models` reports drift. Model sync promotes new Codex slugs in `approve` or `auto` mode and skips pinned aliases.

The full description, including the delegation limits, the 14-element prompt contract, the verification flow and the comparison with other tools, is in [docs/HOW-IT-WORKS.md](https://github.com/domattioli/agents_Inc/blob/main/docs/HOW-IT-WORKS.md).

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 6. Limitations

- Cost savings and accuracy against a baseline are not measured. Passing local tests show that the code behaves as written, not that it is reliable in production.
- The governed path is off by default, so a fresh install does not run the enforced cross-vendor review.
- Cross-vendor review catches disagreement between models. It does not catch a blind spot that both vendors share.
- Deterministic checks cover what a script can express, such as a file, a quote or an exit code. They do not replace human judgment on scope or design.
- Free-model capacity varies: a probe on 2026-09-29 found 429 or capacity errors on several free models ([docs/BENCH.md](https://github.com/domattioli/agents_Inc/blob/main/docs/BENCH.md)). Artifacts stay local; remote publication (Bindle Backend B) is not built.

Updates: new sessions and `agents-inc doctor` tell you when a newer release is on PyPI (one check a day; `AGENTS_INC_NO_UPDATE_CHECK=1` turns it off).

Found a bug or want a feature? `agents-inc report bug --title "..." --body "..."` (or `report feature`) prints a draft issue with your version, doctor result and OS; home paths become `~`. Add `--submit` to file it on GitHub with your own `gh` login.

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 7. Documentation

| File | Reader |
|---|---|
| [docs/START-HERE.md](https://github.com/domattioli/agents_Inc/blob/main/docs/START-HERE.md) | New users: setup, providers, keys, first job |
| [docs/HOW-IT-WORKS.md](https://github.com/domattioli/agents_Inc/blob/main/docs/HOW-IT-WORKS.md) | Operators and agents: dispatch, verification, comparison, HTTP bridge |
| [docs/EXTENDING.md](https://github.com/domattioli/agents_Inc/blob/main/docs/EXTENDING.md) | Adding a vendor, model, task class or domain |
| [docs/DECISIONS.md](https://github.com/domattioli/agents_Inc/blob/main/docs/DECISIONS.md) | Binding rulings, with rationale and evidence |
| [CONTEXT.md](https://github.com/domattioli/agents_Inc/blob/main/CONTEXT.md) | Glossary: CEO, CoS, Lead, Worker, Mandate, Home repo |
| [skills/workerbee/QUICKREF.md](https://github.com/domattioli/agents_Inc/blob/main/skills/workerbee/QUICKREF.md) | Short form of the dispatch rules |
| [docs/RELEASING.md](https://github.com/domattioli/agents_Inc/blob/main/docs/RELEASING.md) | Release runbook |

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>

## 8. Citation and license

The DOI for all versions is [10.5281/zenodo.22670100](https://doi.org/10.5281/zenodo.22670100). GitHub's "Cite this repository" button reads [CITATION.cff](https://github.com/domattioli/agents_Inc/blob/main/CITATION.cff).

agents_Inc is licensed under the PolyForm Small Business License 1.0.0, with one added term that forbids use for AI or machine-learning training. The full terms are in [LICENSE](https://github.com/domattioli/agents_Inc/blob/main/LICENSE).

<div align="right"><a href="#agents_inc"><sub>^ Back to top</sub></a></div>
