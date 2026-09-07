# Session handoff: agents_Inc

- **Transfer:** Paste this block into a fresh Claude Code session started in `~/Projects/agents_Inc`.
- **Scope:** It assumes no memory of the session that produced it.
- **Updated:** 2026-09-07.

---

## Project

- **Repository:** `agents_Inc` at github.com/domattioli/agents_Inc. Formerly `agents_for_dummies` (renamed 2026-09-07, same history).
- **Local clone:** `~/Projects/agents_Inc`.
- **Separation:** QuADMESH-RL is a separate project in a separate session.
- **Hard stop:** Do not touch QuADMESH-RL.

## What this project is

- **Target user:** Tim, a practicing lawyer on a Mac.
- **Acceptance test:** Tim installs Claude Code and Codex, logs both in, pastes one repo URL to his agent, and says “set this up for me.” The agent does the rest unattended.
- **Design rule:** Every design decision serves that flow.
- **Capabilities:**
  - Delegation sends work to cheap models.
  - Memory preserves state across sessions.
  - Governance provides safe defaults across session changes.
- **Modes:** Lawyer, scientist, and engineer.

## Read these first

1. `docs/PLAN-MVP.md`: The 215-line build plan authored by gpt-6-astra at high effort. It is decided rather than exploratory and is the spec.
2. `skills/workerbee/SKILL.md`: Contains supervision discipline. Skim the protocol steps and read Step 2 and Step 3a in full.
3. `docs/HOW-IT-WORKS.md`: Describes the system in compressed form.
4. `docs/START-HERE.md`: Explains the system to Tim.

Do not read all 93 skills in `~/Projects/DomI`.

Mine `session-resume`, `verify-independently`, and `plugin-install-with-vendored-fallback` without vendoring them. Convert the principle instead.

## Settled decisions

### MVP (original 2026-09-05 scoping — superseded, see below)

- **Scope:** Delegation, memory, and governance are all included.
- **Vendors:** Use Claude Code and Codex only.
- **Deferred providers:** Gemini, Mistral, and OpenRouter are post-MVP.
- **Keys and spend:** No API keys, key rotation, or spend guard on day one.
- **Consequence:** Codex is the cheap tier, and Gemini-first chains in `skills/codex-bridge/reference/routing-policy.md:47` are wrong for Tim.
- **Superseded:** Gemini, Mistral, and OpenRouter are live today as optional free-tier grunt/review vendors (`workerbees/routing.json`, `docs/DECISIONS.md`). Treat this block as historical scoping, not current state.

### Components

- **projectmem:** Depend on it, pin it, and ship it inside a private runtime.
- **bindle:** Reimplement the ledger only; skip the git/Obsidian bridge.
- **spec-pressure-test:** Fold it into a maintainer gate rather than a runtime skill.
- **Hooks:** Ship zero installed hooks because they are client-specific and portability costs more than they are worth.
- **First win:** Document analysis and writing in all three modes.
- **Excluded from MVP:** Statusline, HTTP bridge (`bridge.py` stays but is deferred), Codespaces, OCR/scanned PDFs, agent fleets, and recursive delegation.

## State of the repo

- **Main:** `main` is healthy with 55 files. Both histories are merged, and remote main’s commit remains an ancestor.
- **Work:** Nothing is in flight, and there is no open PR.
- **Recent tools:**
  - `skills/codex-bridge/scripts/poll.sh` reports `RUNNING`, `QUIET`, `RESUMED`, `DONE`, `DIED`, or `TIMEOUT`, one line per change, never content. It was self-tested in both directions.
  - `skills/codex-bridge/scripts/watch.sh` provides a filtered live stream for a human in another pane and is deliberately separate from poll.
  - Polling is now the default discipline in workerbee Step 3a.

## Where to start

### Phase 1

- **Scope:** Build the signed pilot capsule, both CLI adapters, Markdown source to cited brief, and deterministic quote checks.
- **Duration:** 5–7 engineer-days.
- **Value:** It is independently useful as a sourced-Markdown analysis tool and ships as a labeled pilot rather than v1.

### Closed gaps

Three gaps closed 2026-09-05. See `docs/DECISIONS.md`.

1. **Gap 1:** Tier routing now uses probe and benchmark and is CTO-owned.
2. **Gap 2:** `--bare` is verified and excluded.
3. **Gap 3:** `agent_runner.py` now emits `returned`, and the `verify` subcommand promotes it.

Read `CONTEXT.md` for the glossary and `docs/adr/`.

### Original gaps

- **Gap 1:** The plan assigned roles by vendor—`Claude driver -> Codex worker, Claude supervisor review`—with delegation depth 1 and one active job per workspace, but did not assign models to summarize, extract, draft, or review.
- **Gap 2:** The plan depended on Claude Code’s `--bare` flag disabling subscription OAuth, but nobody had verified that claim against the logged-in CLI.
- **Gap 3:** `skills/codex-bridge/scripts/agent_runner.py:248` promoted exit code 0 directly to `succeeded`, while the plan required six states.

## How to work here

### Supervision

- Delegate implementation, supervise it, and have cheap models write while you verify.
- Never accept a delegate’s self-reported gate. Three false GREENs occurred in the session that produced this plan.
- Poll every dispatch that outlives one tool call.
- Agent prompts use caveman ultra. `docs/START-HERE.md` does not because it is the non-coder’s door.

### Secrets

- Never read or print `~/Projects/.env`, `~/.codex/auth.json`, or any `*token*`, `*secret*`, `*.pem`, or `*credentials*` file.
- Never put a key in a prompt to any model.

### Collaboration

- Another agent works in this repo and has renamed it twice.
- Fetch before pushing and reconcile instead of force-pushing over its commits.

## Open question

### `docs/START-HERE.md`

- **Question:** Should it be compressed to caveman ultra like the other docs?
- **Recommendation:** No, because it is the first document a non-coder reads.
- **Status:** The question is not yet ruled on.
