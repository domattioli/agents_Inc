# Benchmark — `speckit-pipeline`

> Generated from `templates/benchmark.md.tmpl` (mandate per DomI #21, 2026-05-18).
> Every version bump in `MANIFEST.md` must add a row here justifying the bump with a measured delta.

## Metric

`manual_speckit_command_invocations_per_feature` — number of separate spec-kit commands an operator must issue by hand to take one feature from description to implemented change. Lower is better. Baseline is the manual chain (`/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-checklist` → `/speckit-analyze` → `/speckit-implement`, plus each hand-authored analyze-finding fix) = 7+ invocations. Target with this skill = 1 invocation plus one round of clarify answers.

## Measurement protocol

- **Fixture:** the DomI dogfood run that built this skill (spec `017-speckit-workflow`), plus any subsequent `speckit-pipeline` invocation.
- **Procedure:** count operator-issued `/speckit-*` commands from feature description to `implement` completion, with and without the skill.
- **Sample size:** 1 (this skill's own construction) for the v1.0 baseline; accumulate across real invocations for later rows.

## Results

| Version | Date | Metric | Baseline | Observed | Delta | Evidence |
|---|---|---|---|---|---|---|
| v1.0 | 2026-07-03 | `manual_speckit_command_invocations_per_feature` | 7+ (manual chain) | 1 (single `/speckit-pipeline` invocation + one clarify round) | −6 (≈−86%) | spec `017-speckit-workflow`; development-branch commit history |
| v1.1 | 2026-07-03 | `manual_speckit_command_invocations_per_feature` (unchanged metric — v1.1 targets a different quality axis, see Not-measured) | 1 (v1.0) | 1 (still one invocation; `--yes` runs no longer require a human at all) | 0 (no regression) | v1.0's `--yes` produced a spec with zero clarification answers (literal skip). v1.1 keeps the invocation count flat while fixing that: `--yes` now spawns `clarify-surrogate` to answer grounded, so a fully unattended run's *deliverable quality* no longer degrades relative to an interactive run. This is a quality fix, not an invocation-count fix — see Not-measured for the metric that actually needs tracking. |

## Not-measured versions

| Version | Reason | Plan to backfill |
|---|---|---|
| v1.1 | The quality claim this version makes — "unattended `--yes` runs get clarification answers as good as a human's" — needs its own metric (e.g. `spec_rework_events_per_surrogate_answered_run` vs. per human-answered run), not the invocation-count metric this skill already tracks. No real unattended run has happened yet to measure against. | Backfill once `speckit-pipeline --yes` has run for real ≥3 times; compare downstream rework (spec amendments post-implement) between surrogate-answered and human-answered runs. |
| v1.3 | Docs-only change (added the "Analyze vs. converge" clarification + `speckit-converge` future-work note). No behavior change, so the invocation-count metric is unaffected and there is nothing to measure. | N/A — no measurable delta by construction. If/when `speckit-converge` is ported and wired as a phase, that behavior change gets its own measured row (e.g. `post_implement_convergence_gaps_closed_per_run`). |
| v1.4 | Adds `--plan-only`/`--allow-required-skip` (opt-out required-phase guard, #405). The invocation-count metric is about hand-issued command *count* per feature, which this change does not affect — it adds phase-set *optionality* (planning-only/checkpoint runs), not fewer commands. The real value is avoiding the undocumented manual-orchestration-halt workaround the QuADMESH-RL spec-015 run used. | Would need a different metric (e.g. `manual_orchestration_halts_per_planning_only_run`, target 0). Backfill once ≥3 real planning-only pipeline runs use `--plan-only` instead of the manual halt. |
| v1.5 | Adds provider-agnostic classes (new default mode) + `--legacy` fallback. The invocation-count metric is unaffected — same 1-invocation shape, this change is about dispatch-target/effort/mode selection, not command count. | Needs its own metric, e.g. `pipeline_runs_completed_without_hardcoded_model_drift` or `dispatch_class_resolution_failures_per_run` (falls back to legacy table when `docs/governance/ROUTING-RANKING.md` is absent). Backfill once ≥3 real new-mode runs have executed across at least one consumer repo lacking that file. |
