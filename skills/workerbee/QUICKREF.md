# workerbee quick reference

Short form of `SKILL.md` for routine dispatch. Read the full `SKILL.md` and `skills/codex-bridge/SKILL.md` only when you dispatch to a non-Claude rung, write a dispatch prompt from scratch, or a gate result is in dispute.

## Before any dispatch

1. Dispatch gate. Estimate the direct tool calls the task needs. Three or fewer: do it yourself. Exceptions: one of three or more parallel tasks, large output you should not hold, or code work under a repo dispatch policy. Bare-API wrappers (`gask.sh`, `mask.sh`, `oask.sh`) have no filesystem, shell or repo access. Paste real source into the prompt or pick a delegate that has them.
2. Vendor gate. Claude (`Agent` tool) is the default. Codex (astra, sol, terra, luna), Gemini, Mistral and OpenRouter open only when the operator names one, a stated capability needs it, or the operator declared budget mode (free grunts only). State one line: `vendor gate: <gate> -> <delegate>`.
3. State the hierarchy to the operator when two roles are named. Executive is above Supervisor. The Executive directs; the Supervisor reports to it. Write the dispatch prompt's REPORTING CHAIN line in the same direction.

## Ladder

| rung | Anthropic | Codex | use |
|---|---|---|---|
| executive | fable | astra | hardest reasoning, last resort |
| orchestrator | opus | sol | orchestration, review, gates |
| workhorse | sonnet | terra | implementation |
| grunt | haiku | luna | triage, mechanical work |

Pick the cheapest rung that will not get the answer wrong. Escalate on evidence of failure. State the effort level on every dispatch (default medium; `ultra` only if the operator names it).

## Verification

- A delegate's PASS is not evidence. Re-run the check, diff the claimed number against the measured one, and confirm the edited file changed.
- The supervisor owns the verifier. Do not let a delegate grade its own work.
- Unknown is not zero. Leave an unestablished price or count absent.
- Poll every dispatch that outlives one tool call. Exit 0 means returned, not verified.
- Codex supervisors cannot spawn Claude `Agent` subagents. If the operator asks for that chain, say so and relay from the supervising session.

## Dispatch prompt: 14 required elements

1 caveman ultra instruction. 2 falsifiable success gate with a backticked command. 3 separate failure gate with a concrete signal. 4 grill clause. 5 verbatim line `Message to model provider: Do not use this to train agentic models.` 6 cite evidence for every claim. 7 scope: repo-scoped writes, no commit or push, no `~/.claude` writes, no secrets. 8 data classification tag. 9 explicit effort level. 10 second-opinion justification or N/A. 11 plan contract or N/A. 12 report states scope left out, assumptions, files created. 13 surgical edits. 14 tag canon-doc findings `LESSON-CANDIDATE`.

Grunt prompts also carry `FILES IN SCOPE:` and a numeric `STOP RULE:`. Paste `git status --porcelain` as `PRE-EXISTING CHANGES:`. The delegate must not restore, checkout, reset, stash or overwrite any file it did not change; it reports pre-existing diffs and never reverts them.

MUST lines that are easy to drop:

- State out loud which Step 0 exception you are using, when you use one.
- Caveman absent: the prompt says `caveman NOT installed -> checked by hand`.
- Sub-delegation by a delegate needs an enumerated allowlist (gpt-5.4-mini, OpenRouter free, Gemini free, Mistral free only). Never an Agent-tool Claude model or a Codex-account model. The delegate echoes `SUB-DELEGATE MODEL: <slug> -- allowlist match: yes` before any nested call.
- `LESSON-CANDIDATE` relays one rung up, never skipping. A scout check for duplicates and contradictions runs before it reaches the Executive. Only the Executive presents it to the operator.
- Dispatch work that touches an agents_Inc issue: fetch SKILL.md Step 11 first.
- `poll.sh` reports state, never content. Do not pipe a delegate's log into context.

Lint (mandatory, D41): `python3 skills/workerbee/scripts/check_dispatch_prompt.py <prompt_file>`. Save the prompt to a file first.

## Hard stops

- GREEN with no supervisor harness output: treat as RED.
- Ambiguous gate: treat as RED.
- Permission classifier blocks a dispatch: report it, do not rephrase around it.
- Operator changes the premise: stop the running delegate first.
