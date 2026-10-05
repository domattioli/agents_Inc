# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] — 2026-10-04

### Added

- D47 — `agents-inc dispatch` wraps the dispatch loop.
- D48 — Fan-out cap for delegation.
- D49 — Codex tool access by rung.
- D50 — Codex becomes optional; both-optional deferred to v1.0.
- D51 — Credential-blind dispatch broker.
- D52 — Model pins, drift warnings, operator-decided bumps.
- D53 — QUICKREF loads by hook on first dispatch.
- D54 — delegate turns (`--resume` for Claude and Codex, broker `resume` tool) and a live `ask_lead` channel from a running Worker to its Lead.
- D49.1 — luna accepts `--tools` and `--write` like the other Codex aliases.
- LICENSE: PolyForm Small Business License 1.0.0 plus a licensor-added term that forbids AI/ML training use.
- First PyPI package, `agents-inc` (import name `agents_inc`), built and published by a tag-triggered release workflow.
- Citation metadata for 0.2.0 in `CITATION.cff` and `.zenodo.json`.

## [0.1.0] — 2026-10-01

First tagged release. The project is experimental: the governed path
(`WORKERBEES_GOVERNANCE`) is off by default.

### Added

- Governed routing across Claude, Codex, Gemini, Mistral, OpenRouter, and an
  opt-in local ollama pilot, with deterministic verification, cross-vendor
  review, and an append-only ledger.
- `agents-inc` installer and launcher: install, repair, doctor, rollback, and
  uninstall, with receipt-owned and reversible changes to host configuration.
- Host wiring: a managed instruction block and session hooks in each detected
  host (Claude Code, Codex, Gemini).
- `@alias` side questions from inside a session (`at_route` hook), including
  `@openrouter`. The installer now owns the hook and the alias links (#41, #38).
- Host ledger: delegated calls made from the host session (Agent, Task, and
  DelegateAgent) leave a dispatch row, and `agents-inc ledger append` and
  `agents-inc ledger pending` record verified returns (#36).
- Ledger fields for effort, tokens, cache use, and files created, plus a
  time-window join against usage data (#36).
- Workerbee skill: rung names, a generated tier table with a drift check, a
  rule to keep a delegate until its context ceiling (#28), and a fixed dispatch
  header with fill-in slots and a renderer (#36, #4).
- Persona guard: an Agent or Task description that starts with a Codex persona
  name (astra, sol, terra, luna) is denied, and duplicate spawns of the same
  task from another session raise a warning (#17, #13).
- Transcript recovery helper for interrupted delegates (#13).

### Fixed

- Provider health reports how fresh each result is, and the OpenRouter key is
  found under either name, preferring `OPENROUTER_API_KEY` (#22).
- The launcher runs from any directory and reports a missing install (#35).
