# Dispatch slots: per-task contract elements

Spec 016. Fill each `{{NAME}}` slot for one dispatch, then append
`skills/workerbee/header.md` (or a contract-reference line naming it, for a
delegate that can read files). `skills/workerbee/scripts/render_dispatch.py
--slots <json>` does both from a JSON object keyed by slot name; it exits 2
naming any required slot that is missing or empty. NOTES defaults to `none`;
STYLE may stay empty. The renderer strips the header's markdown title and
authoring comment and emits header text from the CAVEMAN line.

The renderer uses the first `text` code block below as the template.

```text
ROLE: {{ROLE}}
TASK: {{TASK}}
CONSTRAINTS: {{CONSTRAINTS}}
OUT OF SCOPE: {{OUT_OF_SCOPE}}
FILES IN SCOPE:
{{FILES_IN_SCOPE}}
STOP RULE: {{STOP_RULE}}
SUCCESS GATE: {{SUCCESS_GATE}}
FAILURE GATE: {{FAILURE_GATE}}
PRE-EXISTING CHANGES (pre_dispatch_snapshot.py snapshot and its verify command; never restore, checkout, reset, stash, or overwrite these files; the scope gate is the verify command, which hashes them):
{{PRE_EXISTING_CHANGES}}
NOTES (path under the dispatch scratchpad, or none; rewrite whole per milestone, under 60 lines; notes are not evidence, re-verify any fact taken from them in the report): {{NOTES}}
SUB-DELEGATE MODEL ALLOWLIST: {{ALLOWLIST}}
FAN_OUT: {{FAN_OUT}}
CLASSIFICATION: {{CLASSIFICATION}}
EFFORT: {{EFFORT}}
SECOND-OPINION JUSTIFICATION: {{SECOND_OPINION}}
PLAN CONTRACT: {{PLAN_CONTRACT}}
{{STYLE}}
```

Worked example (read-only scout, every slot filled; render appends header.md below it). JSON source: `skills/workerbee/tests/fixtures/example_slots.json`.

```text
ROLE: Grunt scout (haiku, Agent tool), dispatched by Supervisor (opus) in /path/to/repo.
TASK: Read-only scout. 1. Read agents_inc/policy.py. 2. List every function name that contains the word route, with file:line. 3. Return the list; write nothing.
CONSTRAINTS: read-only; no file writes; no network; at most 10 tool calls. Stop-on-block: if a hook or permission classifier blocks a tool call, stop and hand back to the dispatcher; never switch tool to route around it.
OUT OF SCOPE: editing any file; judging routing design; running unittest suites.
FILES IN SCOPE:
none (read-only scout)
STOP RULE: stop after 2 failed reads of the same file; report RED and paste the last command output in a fenced block.
SUCCESS GATE: `grep -n 'def .*route' agents_inc/policy.py` output matches the returned list line for line.
FAILURE GATE: any name missing from the list versus `grep -n 'def .*route' agents_inc/policy.py`, or any write reported by `python3 skills/workerbee/scripts/pre_dispatch_snapshot.py verify <snapshot>`.
PRE-EXISTING CHANGES (pre_dispatch_snapshot.py snapshot and its verify command; never restore, checkout, reset, stash, or overwrite these files; the scope gate is the verify command, which hashes them):
snapshot <snapshot>; verify with `python3 skills/workerbee/scripts/pre_dispatch_snapshot.py verify <snapshot>` (no --allow: scout writes nothing).
NOTES (path under the dispatch scratchpad, or none; rewrite whole per milestone, under 60 lines; notes are not evidence, re-verify any fact taken from them in the report): none
SUB-DELEGATE MODEL ALLOWLIST: none -- do all work yourself
FAN_OUT: width 0, total 0, depth 0
CLASSIFICATION: internal (repo source, non-secret)
EFFORT: effort control unavailable on this transport; intended level = low
SECOND-OPINION JUSTIFICATION: not applicable -- grunt rung, no escalation trigger fired
PLAN CONTRACT: not applicable -- deliverable is not a plan.
```

## Slots

| slot | element | content |
|---|---|---|
| ROLE | context | rung, model, and who dispatched the delegate |
| TASK | context | exact work, files to read first, numbered steps |
| CONSTRAINTS | H4 | hard limits the work must respect; rendered line-start `CONSTRAINTS:` |
| OUT_OF_SCOPE | 12, H4 | work the delegate must not do; rendered line-start `OUT OF SCOPE:` |
| FILES_IN_SCOPE | 7 | one path per line; the only paths the delegate may write |
| STOP_RULE | Grunt | a number of failed attempts, then report RED |
| SUCCESS_GATE | 2 | commands in backticks with the expected output |
| FAILURE_GATE | 3 | commands in backticks or conditions that make the task RED |
| PRE_EXISTING_CHANGES | 7 | `<snapshot>` placeholder: the dispatch wrapper (`agents_inc/install/dispatch.py`) fills it with the snapshot path after capture; hand-written prompts put the path from `pre_dispatch_snapshot.py capture <out.json>` plus the verify command `pre_dispatch_snapshot.py verify <out.json> --allow <path>...` |
| ALLOWLIST | 7 | models the delegate may spawn, or `none — do all work yourself` |
| FAN_OUT | D48 | `width <n>, total <n>, depth <n>`; optional: the renderer fills the rung default from a `RUNG` or `MODEL` slot, else Orchestrator (`width 3, total 6, depth 2`); Workhorse `2, 4, 1`; Grunt `0, 0, 0` |
| CLASSIFICATION | 8 | public, internal, or confidential, with the reason |
| EFFORT | 9 | intended effort level, and whether the transport can set it |
| SECOND_OPINION | 10 | why this rung, or `not applicable` with the reason |
| PLAN_CONTRACT | 11 | plan deliverable rules, or `not applicable — deliverable is not a plan.` |
| NOTES | optional | default `none`; a path must sit under the dispatch scratchpad, never the repo or home |
| STYLE | optional | empty by default; see below |

D51 broker: a Lead sends these slots inline as `slots` in `<run-dir>/inbox/<id>.request.json`
(write `.tmp`, then rename; keys schema_version, request_id, model, effort, tier, slots; never PERMISSION_MODE or credential paths).
It waits with `agents-inc dispatch --wait <run-dir> <id> [--timeout 600]` (1 s polls; exit 124 on timeout), reads `<run-dir>/<id>.report.md`; `inbox/lead.done` stops the broker.

## STYLE slot (experimental, #4)

Opt-in, for extractive and summarization dispatches only. It is not
re-tested in this change. Caveman wins on conflict (operator ruling
2026-10-01): the #4 "Revised template" asked for arrows and abbreviations,
which caveman bans, so the value below drops both:

```text
HARD CONSTRAINT: Default to fragments and labels, NOT normal prose. Follow caveman rules: no arrows, no invented abbreviations; standard acronyms only.
A full grammatical sentence is allowed ONLY where a fragment would lose real precision
(negation scope, conditional/causal clause, operator precedence). Outside those cases,
one complete sentence = you failed the task, rewrite it. When you do use a full sentence,
it should be rare and load-bearing, not a lapse back into prose by default.
```
