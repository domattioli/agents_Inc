# Build plan 2: 3NF store + model catalog + remaining (2026-09-05, fable)

Machine doc. caveman ultra. Reader = Opus orchestrator. Inherits `ORCHESTRATION-HANDOFF.md` dispatch/verify/escalate rules verbatim. CEO rulings this plan: build 3NF now (D15 = 3NF, never BCNF); mistral dropped (key dead, no rotation); `sol` confirmed listed in codex → may enter routing (CEO consent, explicit); codex quota out until ~03:00 local → codex-dependent steps time-gated.

## S1 3NF store (first, blocking)
Source of truth = `docs/governance/SCHEMA-3NF.md` DDL (42 tables, 2 views, q1–q5; fable-verified loads in stdlib sqlite).
| T | What | Builder | Reviewer | Gate |
|---|---|---|---|---|
| 1 | `workerbees/schema.py`: DDL extracted from SCHEMA-3NF.md ```sql blocks at import (parse, not copy → doc stays canonical); `init(conn)`; `SCHEMA_VERSION` | H | S | `tests/test_schema.py`: every table in doc exists in `:memory:`; q1–q5 execute; re-init idempotent |
| 2 | `workerbees/store.py`: write API mirroring ledger emit + control ops → `vendor/provider/model/route/run/family/request/node/node_event/usage/lineage/graph_edge/legacy_parent/frontier_gate/decision/reservation/replay/cancellation/envelope*`. Route freezes alias→model at insert (snapshot rule) | H | S | FD tests: insert same key twice → UNIQUE fail; no derived col stored (node has no vendor col; reservation has no family col) — assert via `PRAGMA table_info` |
| 3 | Dual-write flag `WORKERBEES_STORE=jsonl\|sqlite\|both` (default `both`); `ledger.py` + `control.py` call `store` when set. jsonl path byte-identical when `jsonl` | H | S | 315 tests green in all 3 modes; new tests compare ledger JSONL rollup vs q5 rollup equal |
| 4 | `tools/migrate_to_3nf.py`: JSONL ledger + `control.sqlite` → store; idempotent; report counts | H | S | round-trip test on tim+dom fixtures: JSONL→store→Mermaid == ledger Mermaid |
| 5 | Ledger lint backend on SQL: depth lint (with cycle guard, closes ledger debt), other-vendor reviewer, frontier gate (q4), rollup (q5) → `ledger.lint(source="sqlite")` | H | S | same lint verdicts jsonl vs sqlite on fixtures |
| 6 | Finish SCHEMA-3NF.md missing sections: migration plan (from T4), CEO open questions ≤5, per-agent cost line. Replace STATUS trailer | H draft | S | doc loads + q1–q5 still verified by script |
| 6b | TIME-GATED (codex back ≥03:00): `quota_probe.sh` QUOTA_OK → luna or sol FD review of doc + DDL; gpt-5.4-mini DDL lint. Log verdict in DECISIONS | luna/sol | — | review of record appended to doc |

## S2 model catalog + non-blind OpenRouter routing
| T | What | Builder | Reviewer | Gate |
|---|---|---|---|---|
| 7 | `workerbees/models.json`: per-model profile {vendor, provider, tier, tasks_good[], tasks_bad[], ctx_hint, cost_class, status}. Anthropic: haiku, sonnet, opus, fable. OpenAI/codex: gpt-5.4-mini, gpt-5.6-luna, sol (tier=mid, `status: unprobed`), gpt-6-astra. Gemini: 2.5-flash, flash-lite. Mistral: small → `status: unavailable`. OpenRouter: all 22 from `docs/free-openrouter-models.md` (qualitative fields from doc, `status: unprobed`). Machine doc = caveman ultra strings | H (G draft ok) | S | JSON loads; every routing.json model present; every OR model in doc present; no key-like strings |
| 8 | `router.py`: OpenRouter pick = `models.json` lookup by task (extract/summarize/draft/review-draft) + ordered fallback list on 429/503/empty; `openrouter/auto:free` = last resort only. Log chosen model in ledger node (already `model` col) | H | S | test: task extract → named model not auto; 429 stub → next in list; auto only after list exhausted |
| 9 | `doctor.py`: OR model probe = PONG + 1 fixed classify sample per model → `status: probed_ok\|probed_fail` written to a runtime cache (not models.json); results table appended to `docs/BENCH.md` (human doc D14) | H | S | ≥1 real probe run; failures logged not hidden |
| 10 | routing.json: add `sol` to codex mid tier as alt (`"codex": ["gpt-5.6-luna","sol"]` ONLY if router supports list; else leave, log). CEO consented 2026-09-05. Verify `sorted(keys)` unchanged | H | S | router tests green; DECISIONS entry |

## S3 control.reserve run-level exclusivity (ASSESSMENT §3)
T11: `lease` table (S1) backs run-level lock; two reservations same run_id concurrent → second denied `run_busy`, audited. H builds, S reviews. Gate: concurrency test with threads.

## S4 token budgets
T12: `run_budget` table wired; envelope carries budget; policy denies `budget_exceeded` when `usage` sum ≥ budget; shadow mode audits only. Gate: matrix test 3 modes.

## S5 TIME-GATED codex isolation probe
T13: when QUOTA_OK → `scripts/isolation_probe.sh codex` → expect 3/3 CLEAN; log. If LEAK → escalate fable.

## S6 issue #1 delegation-pattern mining
T14: H reads `docs/DECISIONS.md` + git log + ledger JSONL → `docs/PATTERNS.md` (human doc D14): recurring failures (haiku false-PASS, weakened gates, scope creep) + counter-rules. S review. Comment on issue #1, close if satisfied.

## S7 bench
T15: `bench.py` N≥5 on tim+dom, store=both, governance=enforce → `docs/BENCH.md` table. Gate: verified/needs-review unchanged vs off.

## Order
S1 T1→T5 serial (shared files) → T6 → S2 T7,T8 parallel with S3 T11 (disjoint) → T9,T10 → S4 → S6,S7 → gated T6b,T13 when codex back.

## Dispatch rules delta
- Codex unavailable ~3h: H builds, S reviews, G/OR draft. Poll `quota_probe.sh` before any codex use; never loop-poll (1 probe per task boundary).
- Store writes never touch `routing.json`; T10 = only sanctioned edit, one commit alone.
- Commit per T; push after green; DECISIONS append per T. Final report ≤25 lines caveman ultra.
- Escalate to fable per HANDOFF list; plus: if 3NF FD test contradicts SCHEMA-3NF.md DDL → stop, report (doc is canonical, fix doc via CEO).
