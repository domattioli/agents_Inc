# ADR-0001: Hard $0 per-task spend cap

Status: accepted, 2026-09-05. Decided by CEO.

## Context
Tiered routing could escalate to paid frontier APIs when cheap tiers fail. Paid escalation requires paid keys, spend guards, and per-call consent UX, all of which add setup friction for a non-coder.

## Decision
No paid API path exists in the product. Allowed sources: subscription logins (Claude Code, Codex) and free-tier API keys (Gemini, Mistral, OpenRouter). Quota exhaustion pauses the job and tells the user. No silent fallback.

## Consequences
- Simpler setup, no spend guard, no billing surface.
- Some tasks pause instead of completing. Accepted.
- Cost metric measures incremental dollars (always 0) separately from subscription quota consumed.
- Reversing requires adding key handling, spend guard, and consent UX: meaningful cost.
