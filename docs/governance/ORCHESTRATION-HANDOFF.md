# Orchestration handoff → Opus (2026-09-05)

Machine doc. caveman ultra. Reader = Opus 5 orchestrator session. CEO ruling: Opus orchestrates rest of governance slice; fable = big-picture escalation only, invoked ONLY when Opus judges it is spinning wheels.

## State @ handoff
- main = see `git log -1`. 248+ tests green (`python3 -m unittest discover -s tests`).
- Landed: spec 002 ledger; governance T1–T9 (`workerbees/{registry,envelope,policy,control,gateway}.py`, `governance.json`, `protocols.json`); wrappers read keys from `~/Projects/.env` by name.
- In flight at handoff (check `git status`; land or drop): T10 `tools/governance_demo.py` + test; OpenRouter review of gateway stack (`scratchpad/or_gw_review.md`).
- Reviews of record: sonnet on registry/envelope/policy/control/gateway (all findings fixed). gemini-lite "NO DEFECTS" = weak signal, not clearance.

## Remaining (astra plan §6, `docs/governance/ASSESSMENT.md`)
| T | What | Builder | Reviewer | Gate |
|---|---|---|---|---|
| 10 | demo slice: 1 allowed + 1 denied, both traces; real run once | H | OR→G→S | 2 decisions, 1 ledger node, denial 0 calls |
| 11 | `pipeline.py` via gateway (flag off/shadow/enforce); keep 248 tests | H (G draft) | S | off = byte-identical behavior; enforce = every worker call through gateway |
| 12 | `reviewer.py` via gateway; vendor≠worker enforced even w/ supplied route | H | S | test: supplied same-vendor route denied |
| 13 | `doctor.py` probes via gateway; no bootstrap recursion | H | S | probes = root nodes; `doctor.available` never called by gateway |
| 14 | flag matrix tests; seeded faults; zero-call denials; audit fault injection | H | S | all 3 modes × tim/dom fixtures pass |
| 15 | negatives: replay/crash/cancel/concurrency/approval/injection; both-host isolation | H | S | `scripts/isolation_probe.sh` both vendors CLEAN; injected source text cannot change route/policy |
| 16 | operator docs (human → nested-notes + caveman lite + scientist pass), limits, rollout/rollback | luna→S draft, H review | — | D14 compliance |
Then: CONTEXT.md rows for Agent/Capability/Relationship/Decision/Gateway; DECISIONS entry; push.

## Dispatch rules (binding)
- Builders: H = haiku (lands files). Drafters when quota allows: G = gemini `gask.sh --tier cheap`, OR = `oask.sh` (`:free` only). Codex (luna/mini) only when `quota_probe.sh` = QUOTA_OK (reset ~19:41 today). Reviewer S = sonnet fallback; never same vendor as builder for review of record.
- Zero frontier at build time. fable/astra = plan/escalation only.
- One task = one dispatch prompt, caveman ultra, names exact files allowed, "DO NOT commit", asks for `python3 -m unittest discover -s tests 2>&1 | tail -1` VERBATIM (unittest, not pytest).
- Parallel only on disjoint file sets. pipeline.py/reviewer.py/doctor.py = one writer at a time.
- Never let a drafter/lander touch `workerbees/routing.json` (model table). Verify `sorted(json.load(...).keys())` after any JSON edit.

## Verify discipline (non-negotiable)
- Re-run tests yourself after EVERY landing. Delegate PASS ≠ pass. Two haiku false-completions today (fix described not written; pytest output claimed).
- `git diff --stat` before commit; reject scope creep (one agent reverted another's work today).
- Commit per task, push after green. Message: `<type>: <what>` + builder/reviewer line + test count. Trailer:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- Log every probe result + delegate honesty failure to `docs/DECISIONS.md` (append-only).

## Quota fallbacks
- Codex quota out → S reviews, H builds. Gemini 503 → OR. OR 401 → check `~/Projects/.env` key NAMES only, never print.
- `mistral` key expired (operator rotation) → skip.

## Escalate to fable (SendMessage / ask operator) ONLY when
- 3 consecutive delegate attempts on same task fail verification.
- A spec/architecture conflict needs a ruling not in `docs/DECISIONS.md` or `CONTEXT.md`.
- Test count drops or a previously green test goes red for unclear reason.
- A change would touch `routing.json` semantics, D7/D9 policy, or delete/rewrite `ledger.py`.
- Before any `--force`, history rewrite, or touching another session's repo.
Otherwise: decide, log, continue.

## Done criteria for the slice
- `tools/governance_demo.py` real run: allowed trace + denied trace, decision ids, ledger Mermaid.
- `WORKERBEES_GOVERNANCE=enforce` on tim + dom fixtures: verified/needs-review unchanged vs off; every model call has a decision row.
- 0 false accepts on seeded faults; isolation probes CLEAN both vendors.
- Human docs updated per D14; DECISIONS + CONTEXT updated; pushed.
