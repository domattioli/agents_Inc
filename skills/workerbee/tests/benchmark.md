# Benchmark — `budget-mode-fleet`

> Generated from `templates/benchmark.md.tmpl` (mandate per DomI #21, 2026-05-18).
> Every version bump in `MANIFEST.md` must add a row here justifying the bump with a measured delta.

## Metric

`unverified_delegate_claims_accepted_per_session` — count of delegate-reported
GREEN gates the supervisor accepted without independently re-running the check,
where a later measurement showed the claim was false. Lower is better.

Counts only *false* accepted claims, not all accepted claims — the skill's
purpose is catching the ones that were wrong, not adding ceremony to the ones
that were right.

## Measurement protocol

- **Fixture:** session `33338e35-4ce9-43db-8cf0-624adf37e136` (2026-09-04/05),
  statusline four-row campaign — 7 delegate rounds across luna + two haiku
  implementers.
- **Procedure:** for each delegate report claiming a gate GREEN, re-run the
  delegate's own verification command from the supervisor session and compare
  the measured value against the reported one. Count divergences.
- **Sample size:** 7 delegate rounds, 1 session.

## Results

| Version | Date | Metric | Baseline | Observed | Delta | Evidence |
|---|---|---|---|---|---|---|
| v1.0 | 2026-09-05 | `unverified_delegate_claims_accepted_per_session` | 3 (pre-harness, same session) | 0 (post-harness) | -3 | session 33338e35; see below |

Baseline incidents, all in the same session BEFORE the supervisor-owned
harness rule was adopted — each a GREEN accepted on the delegate's word that
measurement later contradicted:

1. Round 6 alignment: reported `COLUMN INDICES 0 12 44 91 124` /
   `LINE WIDTHS 182 154 134 150`; measured
   `row1 [0,12,49,122,214,329,446]`, widths `458/310/227/245`.
   Cause: printed its intended array, not its rendered output.
2. Applied statusline: harness exit 0 accepted, but row labels
   (`SESSION`/`USAGE`/`DELEGATED`/`COST`) had silently vanished from live
   output, and the verify path emitted 4 cell markers for rows holding up to
   7 items — the gate could not see the defect it was meant to catch.
3. Timing: reported `0.664s`; measured `0.461s` against a `0.35s` baseline.

Post-harness rounds reported RED honestly when RED (round 3 self-reported
G3/G4/G7 RED), and the one GREEN that followed reproduced exactly under
supervisor re-run (`rc=0`, columns `0 11 55 102 134` across all four rows,
marker count equal to item count per row).

## Not-measured versions

| Version | Reason | Plan to backfill |
|---|---|---|
| v1.1 | New content (Step 1a/1b/1c: model roster, discovery snippet, effort-tier rule) fixes a *different* failure class — vendor-nickname misidentification + unprompted effort escalation — not the self-graded-gate metric this skill already tracks. No comparable counter exists yet. | Track `vendor_nickname_misidentified_per_session` (count of times an orchestrator reports a real vendor model as "unavailable" or fails to map a nickname before dispatch) and `effort_escalated_without_operator_ask` starting next session that dispatches to Codex; both should be 0 post-v1.1 given Step 1a/1c now name the check explicitly. |

---

_Benchmark for skill `budget-mode-fleet`. SKILL.md: `../SKILL.md`. Issue: #21._
