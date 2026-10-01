# Dispatch slots: per-task contract elements

Spec 016. Fill each `{{NAME}}` slot for one dispatch, then append
`skills/workerbee/header.md` (or a contract-reference line naming it, for a
delegate that can read files). `skills/workerbee/scripts/render_dispatch.py
--slots <json>` does both from a JSON object keyed by slot name; it exits 2
naming any required slot that is missing or empty.

The renderer uses the first `text` code block below as the template.

```text
ROLE: {{ROLE}}
TASK: {{TASK}}
FILES IN SCOPE:
{{FILES_IN_SCOPE}}
STOP RULE: {{STOP_RULE}}
SUCCESS GATE: {{SUCCESS_GATE}}
FAILURE GATE: {{FAILURE_GATE}}
PRE-EXISTING CHANGES (git status --porcelain before dispatch; never restore, checkout, reset, stash, or overwrite them; the scope gate compares against this snapshot):
{{PRE_EXISTING_CHANGES}}
SUB-DELEGATE MODEL ALLOWLIST: {{ALLOWLIST}}
CLASSIFICATION: {{CLASSIFICATION}}
EFFORT: {{EFFORT}}
SECOND-OPINION JUSTIFICATION: {{SECOND_OPINION}}
PLAN CONTRACT: {{PLAN_CONTRACT}}
{{STYLE}}
```

## Slots

| slot | element | content |
|---|---|---|
| ROLE | context | rung, model, and who dispatched the delegate |
| TASK | context | exact work, files to read first, numbered steps |
| FILES_IN_SCOPE | 7 | one path per line; the only paths the delegate may write |
| STOP_RULE | Grunt | a number of failed attempts, then report RED |
| SUCCESS_GATE | 2 | commands in backticks with the expected output |
| FAILURE_GATE | 3 | commands in backticks or conditions that make the task RED |
| PRE_EXISTING_CHANGES | 7 | `git status --porcelain` output before dispatch |
| ALLOWLIST | 7 | models the delegate may spawn, or `none — do all work yourself` |
| CLASSIFICATION | 8 | public, internal, or confidential, with the reason |
| EFFORT | 9 | intended effort level, and whether the transport can set it |
| SECOND_OPINION | 10 | why this rung, or `not applicable` with the reason |
| PLAN_CONTRACT | 11 | plan deliverable rules, or `not applicable — deliverable is not a plan.` |
| STYLE | optional | empty by default; see below |

## STYLE slot (experimental, #4)

Opt-in, for extractive and summarization dispatches only. It is not
re-tested in this change, and it conflicts with caveman on arrows and
abbreviations; the dispatcher chooses one. The value from #4 "Revised
template", verbatim:

```text
HARD CONSTRAINT: Default to fragments, labels, arrows, abbreviations — NOT normal prose.
A full grammatical sentence is allowed ONLY where a fragment would lose real precision
(negation scope, conditional/causal clause, operator precedence). Outside those cases,
one complete sentence = you failed the task, rewrite it. When you do use a full sentence,
it should be rare and load-bearing, not a lapse back into prose by default.
```
