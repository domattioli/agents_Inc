# Prior art: @alias side-question hook

## 1. Verdict
Partial. [inferred] No one found doing the exact thing: a hook that catches the prompt, skips the session model, and uses a per-message `@alias` (exit 2, answer on stderr, plus the `@@` inject variant). Claude Code hook-based model routers do exist, but they route whole sessions or subagents.

## 2. Closest matches
| Name | URL | What it does | How it differs from ours | Tag |
|---|---|---|---|---|
| tzachbon/claude-model-router-hook | https://github.com/tzachbon/claude-model-router-hook | Its UserPromptSubmit hook classifies the prompt, then warns or writes the model for the next session. It also routes subagent spawns. | Works per session, not per question. No block-and-answer. | [verified] README fetched |
| IuriiTurok/auto-model-router | https://github.com/IuriiTurok/auto-model-router | Its UserPromptSubmit hook injects a routing decision. The session may dispatch a worker subagent. Forced with `#model=`. | Advisory only; the session model still runs. Uses `#model=`, not `@`. | [verified] README fetched |
| abroberts14/model-routing | https://github.com/abroberts14/model-routing | A PreToolUse hook sets a default model on Agent spawns that name none. | Covers subagents only. No operator syntax. | [verified] README fetched |
| bmersereau/claude-router | https://github.com/bmersereau/claude-router | Routes by complexity to Haiku, Sonnet, or Opus. | Works per task or session. | [workhorse-reported] |
| aider /model, /ask | https://aider.chat/docs/usage/commands.html | `/model` switches the session model. | A lasting switch, not a one-off question. | [workhorse-reported] |
| Open WebUI /model | https://docs.openwebui.com/features/chat-conversations/chat-features/ | `/model` switches the chat model. | A lasting switch. | [workhorse-reported] |
| Continue.dev @-mentions | https://docs.continue.dev/customize/deep-dives/custom-providers | `@` picks context providers. | `@` means context, not a model. | [workhorse-reported] |
| RouteLLM / Martian / Not Diamond | https://github.com/Not-Diamond/awesome-ai-model-routing | Automatic per-query routers at the API layer. | Sit below the CLI. No operator alias. | [workhorse-reported] |

## 3. What to borrow
- tzachbon's `~`/`<` skip-routing prefix: consider an escape for a literal `@` at the start of a prompt. [workhorse-reported]
- IuriiTurok's `#model=` force syntax: cite it as the nearest syntax precedent. [verified]
- Cite the two Claude Code router hooks, plus RouteLLM and FrugalGPT, as the lineage of cost-routing work. [inferred]

## 4. What is new in ours
- The hook blocks the prompt with exit 2, so the session model never runs, and the answer comes back on stderr. [inferred]
- One syntax offers two modes: `@` gives a side answer, `@@` injects the answer into context. [inferred]
- The same alias reaches both Claude and Codex models. [inferred]

## Gaps
Not searched (the workhorse used 7 of its 15 searches): Cursor, Cline, Zed, Warp, opencode, Msty, Chatbox, big-AGI, TypingMind. [verified]
