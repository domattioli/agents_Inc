# agents_for_dummies — agent instructions

## Documentation audience rule (CEO 2026-09-05, binding)

| Surface | Reader | Wording | Structure |
|---|---|---|---|
| Repo README, START-HERE, HOW-IT-WORKS, EXTENDING, HANDOFF, DECISIONS, BENCH, governance/CEO-BRIEF | human, live + async | caveman lite (trim, stay readable) | nested-notes (outline → scannable) + write-like-scientist pass (precise, concise) |
| Agent prompts, skills/*/SKILL.md bodies, dispatch specs, PLAN-MVP, routing.json comments, governance/ASSESSMENT.md, workerbees/*.json | agent/model/builder | caveman ultra (max compress) | prose (no structure overhead) |

**Enforcement:** Human docs get nested-notes + caveman lite + write-like-scientist before any commit. Machine docs = caveman ultra, no override. Upstream this table into every agent prompt; downstream tasks inherit.

## Coding dispatch — labor rule (binding)

- **Write code:** haiku + free models (gpt-5.4-mini, gemini-flash). Agent writes, pushes to branch, CI gates.
- **Review code:** luna tier (claude-sonnet-4, gpt-5.6-luna). Agent reviews changes, posts inline comments or `LGTM`.
- **Orchestrate/plan:** fable/astra only (fable 5.1, gpt-6-astra). Never for code writing or routine review — only high-judgment dispatch, risk eval, blocked decision unblock.
- **Exception:** explicit operator instruction overrides tier assignment.

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
