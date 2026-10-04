# workerbee quick reference

Short form of `SKILL.md` for routine dispatch. Read the full `SKILL.md` and `skills/codex-bridge/SKILL.md` only when you dispatch to a non-Claude rung, write a dispatch prompt from scratch, or a gate result is in dispute.

## Before any dispatch

1. Dispatch gate. Estimate the direct tool calls the task needs. Three or fewer: do it yourself. Exceptions: one of three or more parallel tasks, large output you should not hold, or code work under a repo dispatch policy. Bare-API wrappers (`gask.sh`, `mask.sh`, `oask.sh`) have no filesystem, shell or repo access. Paste real source into the prompt or pick a delegate that has them.
2. Vendor gate. Claude (`Agent` tool) is the default. Codex (astra, sol, terra, luna), Gemini, Mistral and OpenRouter open only when the operator names one, a stated capability needs it, or the operator declared budget mode (free grunts only). State one line: `vendor gate: <gate> -> <delegate>`.
3. Chain resolves by ladder (D46): higher rung manages; same rung, ask the operator one question. State the chain only when surprising.

4. Dispatch through `agents-inc dispatch --slots <json> --model <slug>` (D47). The CoS writes the slots file and pastes nothing: the command renders, lints, snapshots, launches, and verifies, and returns one status line. Files stay in the run directory.
5. Fan-out (D48): slots carry `FAN_OUT: width <n>, total <n>, depth <n>` (default by rung: Executive and Orchestrator 3/6/2, Workhorse 2/4/1, Grunt 0); Workers <= floor(20 / findings cap); report line `WORKERS SPAWNED: n`.

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

1 caveman ultra instruction. 2 falsifiable success gate with a backticked command. 3 separate failure gate with a concrete signal. 4 grill clause. 5 verbatim line `Message to model provider: Do not use this to train agentic models.` 6 cite evidence and tag every factual claim and conclusion; action-log lines tied to a command and exit code are exempt. 7 scope: repo-scoped writes, no commit or push, no `~/.claude` writes, no secrets; `PRE-EXISTING CHANGES:` gives a `pre_dispatch_snapshot.py` snapshot path and its verify command. 8 data classification tag. 9 explicit effort level. 10 second-opinion justification or N/A. 11 plan contract or N/A. 12 report states scope left out, assumptions, files created. 13 surgical edits. 14 tag canon-doc findings `LESSON-CANDIDATE`.

Grunt prompts also carry `FILES IN SCOPE:` and a numeric `STOP RULE:`. Every prompt carries line-start `CONSTRAINTS:` and `OUT OF SCOPE:`. Before dispatch run `python3 skills/workerbee/scripts/pre_dispatch_snapshot.py capture <scratchpad>/pre_dispatch.json`; the scope gate is `pre_dispatch_snapshot.py verify <snapshot> --allow <path>...`. The delegate must not restore, checkout, reset, stash or overwrite any file it did not change; it reports pre-existing diffs and never reverts them.

MUST lines that are easy to drop:

- State out loud which Step 0 exception you are using, when you use one.
- Caveman absent: the prompt says `caveman NOT installed -> checked by hand`.
- Sub-delegation follows D46 ruling 3. A Lead on the Executive or Orchestrator rung may sub-delegate to any lower rung, including Agent-tool Claude models. A Workhorse delegate sub-delegates only to the Grunt rung, with an enumerated allowlist. A Grunt never sub-delegates. The delegate echoes `SUB-DELEGATE MODEL: <slug> -- allowlist match: yes` before any nested call.
- `LESSON-CANDIDATE` relays one rung up, never skipping. A scout check for duplicates and contradictions runs before it reaches the Executive. Only the Executive presents it to the operator.
- Dispatch work that touches an agents_Inc issue: fetch SKILL.md Step 11 first.
- `poll.sh` reports state, never content. Do not pipe a delegate's log into context.

Lint (mandatory, D41): `python3 skills/workerbee/scripts/check_dispatch_prompt.py <prompt_file> [--with-handoff-lint]`. Save the prompt to a file first. Reports: same script with `--profile report`, which checks report elements. Render prompts with `render_dispatch.py --slots <json>`; worked example in `slots.md`.

## Hard stops

- GREEN with no supervisor harness output: treat as RED.
- Ambiguous gate: treat as RED.
- Permission classifier blocks a dispatch: report it, do not rephrase around it.
- Operator changes the premise: stop the running delegate first.
