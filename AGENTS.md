# agents_Inc — CAVEMAN ULTRA

When `CODEX_BRIDGE_MODE=ultra`:

- Be terse and direct. Send only the context needed for the task; report the result, evidence, and blockers.
- Delegate only to Gemini, Mistral, or Codex. Never fall back to an Anthropic backend.
- Verify delegated work locally before reporting it as complete.
- If no eligible backend is available, stop and say so. Do not silently change modes or providers.

## Documentation style (binding)

CEO 2026-09-05 rule — see `CLAUDE.md` "Documentation audience rule" for the full surface/reader/wording/structure table.

## Delegation model

Canon: `docs/governance/DELEGATION-MODEL.md` (5 roles, 9 speckit phases, Mermaid + phase-actor table). Not restated here.

