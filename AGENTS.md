# CAVEMAN ULTRA

When `CODEX_BRIDGE_MODE=ultra`:

- Be terse and direct. Send only the context needed for the task; report the result, evidence, and blockers.
- Delegate only to Gemini, Mistral, or Codex. Never fall back to an Anthropic backend.
- Verify delegated work locally before reporting it as complete.
- If no eligible backend is available, stop and say so. Do not silently change modes or providers.

