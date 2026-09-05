# CAVEMAN ULTRA

When `CODEX_BRIDGE_MODE=ultra`:

- Be terse and direct. Send only the context needed for the task; report the result, evidence, and blockers.
- Delegate only to Gemini, Mistral, or Codex. Never fall back to an Anthropic backend.
- Verify delegated work locally before reporting it as complete.
- If no eligible backend is available, stop and say so. Do not silently change modes or providers.

## Documentation style (binding)

CEO 2026-09-05 rule — embedded from CLAUDE.md:

| Surface | Reader | Wording | Structure |
|---|---|---|---|
| Repo README, START-HERE, HOW-IT-WORKS, EXTENDING, HANDOFF, DECISIONS, BENCH, governance/CEO-BRIEF | human, live + async | caveman lite (trim, stay readable) | nested-notes (outline → scannable) + write-like-scientist pass (precise, concise) |
| Agent prompts, skills/*/SKILL.md bodies, dispatch specs, PLAN-MVP, routing.json comments, governance/ASSESSMENT.md, workerbees/*.json | agent/model/builder | caveman ultra (max compress) | prose (no structure overhead) |

Enforcement: human docs nested-notes + caveman lite + write-like-scientist before commit. Machine docs = caveman ultra, no override. Upstream this table in every agent prompt.

