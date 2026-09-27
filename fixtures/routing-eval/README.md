# Routing eval

A labeled set of task descriptions for testing routers: how well a router picks the right rung for a task. It works for any router (Haiku, Luna, Jev, a rule set), so the same cases compare them fairly.

## Files

- `cases.jsonl`: one case per line.

| Field | Meaning |
|---|---|
| `id` | `r001` to `r103` |
| `task` | the task text a router sees |
| `source` | `at_route_answers.log` (4 real past tasks) or `written` (drafted 2026-09-27) |
| `category` | column of `docs/governance/ROUTING-RANKING.md`, plus `scouting` |
| `vague` | `true` when the task text is too unclear to route well; a good router should report low confidence on these |
| `suggested_rung` | the drafter's guess, from the routing rule in `ROUTING-RANKING.md` |
| `rung` | the operator's label; `null` until labeled |

Rungs: `free_grunt`, `grunt`, `workhorse`, `orchestrator`, `executive` (CONTEXT.md).

## Labeling

Set `rung` on each line. Only `rung` counts as ground truth; `suggested_rung` is a draft and may be wrong. To limit anchoring on the draft, label a first pass without looking at `suggested_rung`, then compare.

Status: unlabeled. No router has been scored yet.
