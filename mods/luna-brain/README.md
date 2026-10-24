# luna-brain

Spike: a read-only subagent (Read, Grep, Glob) whose model steps are answered by luna through `agents-inc run`, not by Anthropic.

Try it: `claude --plugin-dir mods/luna-brain`, then ask for a subagent of type `luna-brain:luna`.
Each step logs its wall time; check with `claude --debug`. Throwaway code, no write tools.
