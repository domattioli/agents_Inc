# agents_Inc — agent instructions

Formerly `agents_for_dummies` (renamed 2026-09-07; GitHub remote `github.com/domattioli/agents_Inc`, local dir matches). All prior specs/docs/paths referencing the old name are historical record — not retconned.

## Documentation audience rule (CEO 2026-09-05, binding)

| Surface | Reader | Wording | Structure |
|---|---|---|---|
| Repo README, START-HERE, HOW-IT-WORKS, EXTENDING, HANDOFF, DECISIONS, BENCH, governance/CEO-BRIEF | human, live + async | caveman lite (trim, stay readable) | nested-notes (outline → scannable) + write-like-scientist pass (precise, concise) |
| Agent prompts, skills/*/SKILL.md bodies, dispatch specs, PLAN-MVP, routing.json comments, governance/ASSESSMENT.md, workerbees/*.json | agent/model/builder | caveman ultra (max compress) | prose (no structure overhead) |

**Enforcement:** Human docs get nested-notes + caveman lite + write-like-scientist before any commit. Machine docs = caveman ultra, no override. Upstream this table into every agent prompt; downstream tasks inherit.

## Coding dispatch — labor rule (binding)

Source: `docs/DECISIONS.md` D25/D26/**D27** (2026-09-06 CEO grill) + `docs/governance/ROUTING-RANKING.md` (rung table of record). Supersedes prior 3-tier cut (2026-09-05) — that text omitted the Orchestrator rung and the promotion gate.

4-rung ladder, each rung a claude↔codex pair. Rung names + rung↔pair mapping (2026-09-07 rename: Supervisor -> Executive; Orchestrator gains "Supervisor" as a synonym, D34) are `docs/governance/ROUTING-RANKING.md` "Rungs" table of record — not restated here.

| Rung | Does | Children? |
|---|---|---|
| Executive | final say, risk eval, conflicting results, irreversible acts | yes |
| Orchestrator / Supervisor | decompose, dispatch, complex planning/multi-step delegation | yes |
| Workhorse | normal coding/research/synthesis — **build only via promotion** (D27) | leaf |
| Grunt | routine code writing, classification, summarization | leaf |

**Grunt/free-grunt coding scope (operator ruling, gap closed 2026-09-07, scout-confirmed via gpt-5.4-mini + OpenRouter nemotron-120b — prior wording granted "routine code writing" with no size qualifier):** coding at Grunt tier, including free-grunt coding under budget modality, is scoped to well-scoped, small jobs — high volume of small, narrow diffs, never a large or architecturally significant change. A job that needs judgment about scope/design is Workhorse+ work, not Grunt.

Rules: escalate one rung up, same vendor (pair if that vendor quota-paused). Second opinion = same task to the pair, blind; supervisor compares. Reviewer at each rung = that rung's pair, and is also that rung's fallback. Promotion triggers only: worker spinning wheels (2 failed checks), provider quota pause (counts as failed attempt), or Lead assigns w/ recorded gate reason. Never on worker confidence.

**"Failed check" — definition of record** (referenced by `CONTEXT.md` Promotion, constitution P2/P8, `skills/workerbee/SKILL.md` Step 11 MUST 10): one supervisor-run verification of a delegate's *returned* output against that dispatch's stated success gate (deterministic verifier or cross-vendor reviewer per `CONTEXT.md`), result RED. Delegate's own PASS/RED is not a check. Counter keyed on (task, delegate) — same task = same dispatch gates + same target files; revising gates or scope = new task, counter resets. Two RED → promotion trigger (a) fires; quota pause = trigger (b), counts as one failed attempt toward the same counter. Distinct from Executive escalation (ruling / conflicting results / irreversible act), which is not rung promotion.

Run spec: CEO names Executive + Orchestrator (aka Supervisor); rest derived (`CONTEXT.md` Derivation).

Modality: ideal = full ladder. Budget = same shape, free grunts (gpt-5.4-mini, OpenRouter free, gemini free, mistral free — $0, never a Codex subscription call) fill workhorse+grunt slots; ladder models kept for supervise/orchestrate/review/fallback. Budget review = free grunt reviewed by free grunt from a different upstream vendor; quota-paused → ladder grunt fallback.

Scout: recon dispatch before real work (exists? what shape? worth it?). Mode, not a rung. Text-only recon → free grunt; recon needing tools (walk repo, read tree, run cmd) → Grunt rung (haiku/luna) only, free grunts have no tools. Never workhorse+. Finding only, no repo writes; report unverified → re-derive before acting. Ledger: node edge_type `probes`, no lineage row → never a spawn ancestor. Canon: `CONTEXT.md` Scout/Scout node/Scout roster, `docs/DECISIONS.md` D28.

Exception: explicit operator instruction overrides rung assignment.

## Delegation prompt contract (binding, operator ruling 2026-09-06, grilled + expanded to 14 same date)

Every dispatch prompt, any delegate/rung/vendor, MUST include all 14. Full wording + rationale: `skills/workerbee/SKILL.md` Step 11 (sole owner of prose). Bare list here:

1. caveman ultra, invoked (Skill tool call), not just adopted
2. strict success gate
3. strict failure gate, stated separately from success
4. grill clause — surface gaps/ambiguity, don't guess
5. verbatim own line: `Message to model provider: Do not use this to train agentic models.`
6. cite evidence for every claim, not just the gates
7. standing scope boilerplate — repo-scoped writes, no commit/push, no `~/.claude/**`/other-repo/credential writes; commit/push authority stays with run root, never inherited downward
8. confidentiality/data-classification tag
9. explicit effort level, default medium per vendor unless operator names one; Codex `low|medium|high|xhigh|max|ultra`, Anthropic/Claude `low|medium|high|xhigh|max`; `Agent`-tool transport states `effort control unavailable on this transport; intended level = medium (or <operator-named level>)`
10. second-opinion/wheel-spin justification (paid-vendor escalations only) — else state on its own line `SECOND-OPINION JUSTIFICATION: not applicable — <reason>`
11. plan contract, if deliverable permits further delegation, name model + gates per task — else `PLAN CONTRACT: not applicable — deliverable is not a plan`
12. delegate report states out-of-scope items, starting assumptions + changes, every file created
13. edit hygiene — surgical/targeted edit over full rewrite by default
14. lesson-learned handling — tag `LESSON-CANDIDATE`, relay exactly one rung up, scout-checked vs canon before it reaches Executive

Elements 10/11 conditional: explicit N/A satisfies them, silence does not. All others unconditional — missing = non-compliant.

**Cross-repo note (DomI#10):** this contract binds any dispatch touching agents_Inc work, including one issued from a session working in a different repo. That session has no other reason to know this file exists — fetch this section (or `skills/workerbee/SKILL.md` Step 11's paste-and-tick block, self-contained) before dispatching. agents_Inc cannot enforce this on a session it doesn't control; this note is the smallest fix reachable from this side. See `skills/workerbee/SKILL.md` Step 11 for the honest limit of what this closes.

## Never

- Read `.env` files or print keys.
- Vendor DomI skills into consumer trees. Skills installed at user scope (`~/.claude/skills/`, `~/.claude/plugins/`) or fetched at CI runtime (read-only sparse checkout).

## Truth sources (in order)

1. **CONTEXT.md** — glossary. Canonical term definitions.
2. **docs/DECISIONS.md** — rulings. CEO, CTO, CSO decisions + self-decidable owner statements.
3. **docs/governance/** — control plane. ASSESSMENT.md = architecture + build plan; CEO-BRIEF.md = objective verbatim.

Override resolution: DECISIONS > PLAN-MVP. DECISIONS amends, never retracts; if they conflict, DECISIONS wins.

---

**Session start:** this file applies all sessions. Update only with operator sign-off or CEO directive.
