# luna-brain

Spike: a subagent with the same tools, permissions and hand-back as any native subagent, whose model steps are answered by luna through `agents-inc run`, not by Anthropic.

Try it: `claude --plugin-dir mods/luna-brain`, then ask for a subagent of type `luna-brain:luna`.
Each step logs its wall time and prompt size; check with `claude --debug`. Throwaway code.
