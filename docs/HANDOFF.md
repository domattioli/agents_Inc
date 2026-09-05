# Session handoff — agents_for_dummies

Paste the block below into a fresh Claude Code session started in
`~/Projects/workerbees`. It is self-contained: it assumes no memory of the
session that produced it.

Last updated 2026-09-05.

---

You are picking up `agents_for_dummies` (github.com/domattioli/agents_for_dummies,
local clone `~/Projects/workerbees` — the directory name still says workerbees,
the repo was renamed twice). Nothing about QuADMESH-RL is relevant here; that is
a separate project in a separate session. Do not touch it.

## What this project is

A delegation system for people who do not code. The target user is Tim, a
practicing lawyer on a Mac. He installs Claude Code and Codex himself and logs
both in. Then he pastes ONE repo URL to his agent and says "set this up for me,"
and the agent does the rest unattended. **That flow is the acceptance test.
Every design decision serves it.**

Three things it does: delegation (cheap models do the work), memory (state
survives across sessions), governance (safe defaults that survive a session
change). Three modes: lawyer, scientist, engineer.

## Read these first, in this order

1. `docs/PLAN-MVP.md` — the build plan. Authored by gpt-6-astra at high effort,
   215 lines, decided rather than exploratory. This is your spec.
2. `skills/workerbee/SKILL.md` — the supervision discipline. Long; skim the
   protocol steps, read Step 2 (never accept a self-graded gate) and Step 3a
   (poll every dispatch) in full.
3. `docs/HOW-IT-WORKS.md` — the system in compressed form.
4. `docs/START-HERE.md` — what Tim reads. Plain prose on purpose.

Do NOT read all 93 skills in `~/Projects/DomI`. The plan names the three worth
mining (`session-resume`, `verify-independently`,
`plugin-install-with-vendored-fallback`) and DomI policy forbids vendoring them
anyway — convert the principle, do not copy the tree.

## Settled decisions — do not relitigate

- MVP = delegation + memory + governance. All three.
- Vendors = **Claude Code + Codex only.** No API keys, no `.env`, no key
  rotation, no spend guard on day one. Gemini/Mistral/OpenRouter are post-MVP.
  Consequence: the cheap tier is Codex, and the Gemini-first chains in
  `skills/codex-bridge/reference/routing-policy.md:47` are wrong for Tim.
- projectmem: **depend**, pinned, inside a shipped private runtime.
  bindle: **reimplement-minimal** (ledger only, skip the git/Obsidian bridge).
  spec-pressure-test: **fold in** as a maintainer gate, not a runtime skill.
- Zero installed hooks. They are client-specific and portability costs more
  than they are worth.
- First win = document analysis and writing, in all three modes.
- **Excluded from MVP:** the statusline, the HTTP bridge (`bridge.py` stays but
  is deferred), Codespaces, OCR/scanned PDFs, agent fleets, recursive delegation.

## State of the repo

`main` is healthy: 55 files, both histories merged, remote main's commit
preserved as an ancestor. Nothing is in flight. There is no open PR.

Recently landed and worth knowing about:
- `skills/codex-bridge/scripts/poll.sh` — delegate liveness. Reports STATE
  (`RUNNING`/`QUIET`/`RESUMED`/`DONE`/`DIED`/`TIMEOUT`), one line per change,
  never content. Self-tested both directions.
- `skills/codex-bridge/scripts/watch.sh` — filtered live stream for a human in
  another pane. Deliberately not the same tool as poll.
- Polling is now default discipline (workerbee Step 3a), not an option.

## Where to start

Phase 1 of the plan, 5–7 engineer-days: signed pilot capsule, both CLI
adapters, Markdown source to cited brief, deterministic quote checks. It is
independently useful on its own — a sourced-Markdown analysis tool — so it
ships as a labeled pilot, not as v1.

Before writing code, close these three gaps in the plan:

1. **Which model does which task.** The plan assigns roles by vendor
   (`Claude driver -> Codex worker, Claude supervisor review`, delegation depth
   1, one active job per workspace) but never says which model handles
   summarize vs extract vs draft vs review. Decide it and write it down.
2. **The `--bare` claim.** The plan asserts Claude Code's `--bare` flag
   disables subscription OAuth, and its whole adapter design depends on that.
   Nobody has verified it. Test it against the logged-in CLI before building on
   it.
3. **`verified` vs `returned`.** `skills/codex-bridge/scripts/agent_runner.py:248`
   promotes exit code 0 straight to `succeeded`. The plan wants six states.
   This is the smallest change with the largest correctness payoff.

## How to work here

- Delegate implementation; supervise it. Cheap models write, you verify.
  **Never accept a delegate's self-reported gate** — three false GREENs
  happened in the session that produced this plan, every one of them a
  delegate printing what it intended rather than what it measured. Re-run the
  check yourself.
- Poll every dispatch that outlives one tool call.
- Agent-facing prompts are caveman ultra. `docs/START-HERE.md` is deliberately
  NOT — it is the non-coder's door, and compressing it defeats its purpose.
- Never read or print `~/Projects/.env`, `~/.codex/auth.json`, or any
  `*token*` / `*secret*` / `*.pem` / `*credentials*` file. Never put a key in a
  prompt to any model.
- Another agent also works in this repo and has renamed it twice. Fetch before
  you push, and never force-push over its commits — reconcile instead.

## Open question for the operator

Whether `docs/START-HERE.md` should be compressed to caveman ultra like the
other docs. The recommendation on record is no, because that file is the one
thing a non-coder reads first. Not yet ruled on.
