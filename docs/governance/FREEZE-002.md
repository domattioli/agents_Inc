# FREEZE-002: Dispatch Graph Ledger Snapshot

**Commit**: d9704d42cfc4e373f1a3c643bb2ebcc55d9f83b5  
**Date**: 2026-09-05  
**Author**: Governance assessment (Task 1)

## Purpose

Frozen hashes and dispatch call sites for spec-002 (Dispatch Graph Ledger) as baseline for spec-003 (Governance Slice) development. No code modifications; read-only snapshot for audit and policy evaluation.

## File Hashes (SHA256) at HEAD

All hashes computed from working tree at `d9704d4`.

| File | SHA256 |
|---|---|
| `workerbees/ledger.py` | `3adb0a3466fcfe84a2ff4fa0e1105eb0f85646a0def3479a7b4de411c48483ae` |
| `workerbees/pipeline.py` | `d76410690a8efc5e9df5b99915252a11f2d935f4b99c136c888509b64c36f8ec` |
| `workerbees/reviewer.py` | `7a9062ce3fc91661eea4e4a77af30bab99ef4745ad87bbccc668d3bac270bf62` |
| `workerbees/doctor.py` | `fe3726a9f336240e8654a9701abfe07401b017ccd86b31e986df1951b8ab0d53` |
| `workerbees/policy.py` | `44041d9fc65825a0ff1d2325d874e324cec5015a18cb9b58105ef859a1dd9479` |
| `workerbees/router.py` | `3c2804e02ef1f52251febbf52aea9b19e18c0e59787f1eb8da9d25cedcbb88c4` |
| `workerbees/routing.json` | `2b954663e88a9463fabf59eaec5862fa069e44387e1c36d50294936bc792cd59` |

## Dispatch Call Sites

Inventory of all dispatch invocations (`runner()`, `run_worker()`, `review()`, `probe_cli()`) in workerbees tree at freeze point. Column meanings:

- **File:Function** — source location
- **Line** — first line number in source
- **Callee** — which dispatch/runner function is invoked
- **Context** — brief caller identity or parent edge type (from ledger records or flow)
- **Args** — dispatch payload (model, task, provider where applicable)

| File:Function | Line | Callee | Context | Payload |
|---|---:|---|---|---|
| `pipeline.py:brief` | 180 | `runner(cmd, stdin)` | Worker dispatch; parent_id=None, edge_type=None | task=extract, model via route |
| `pipeline.py:brief` | 260 | `runner(cmd, stdin)` | Correction retry; parent_id=worker_node_id, edge_type=corrects | task=extract, model via route |
| `pipeline.py:brief` | 213 | `review(...)` | Reviewer dispatch via route; caller wraps runner invocation (line 46) | source/claims/draft; independent vendor via exclude_provider |
| `reviewer.py:review` | 46 | `runner(cmd, prompt)` | Review worker call; invoked via reviewer.review() from pipeline | Reviewer model cmd + REVIEW_PROMPT |
| `doctor.py:probe_cli` | 29 | `runner(cmd, "reply exactly PONG")` | Health probe; one per provider per run | task=probe, tier=cheap, model from cheap tier |
| `doctor.py:run` | 63 | `probe_cli(p, runner=runner, ...)` | Orchestrator loop; calls probe_cli once per provider | Wrapped runners; results collected |

## Ledger Recording

Both worker and correction paths record dispatch + return via `ledger.record_dispatch()` and `ledger.record_return()`, capturing:
- node_id (uuid)
- run_id (groups one brief execution)
- model, tier, task, provider
- parent_id (None for worker, worker_node_id for correction)
- edge_type (None for worker, "corrects" for retry, "reviews" for reviewer, "probes" for doctor)
- status, seconds, subscription_calls (1 per node)
- gate_reason (filled for frontier tier only)

Reviewer and doctor record directly via pipeline/doctor entry points; no nested recorder.

## Constraints Observed

1. **No spawn from worker**: Workers at `pipeline.py:180,260` invoke only `runner()`, not `review()` or `probe_cli()`.
2. **Independent reviewer**: Reviewer invokes runner only after `pick_model(..., exclude_provider=worker_provider)`, enforcing vendor split.
3. **Doctor isolation**: Probe calls in `doctor.py:63` have separate run_id and no parent edge; results are read-only diagnostics, not acceptance gates.
4. **Ledger capture**: All three paths (worker, correction, review, probe) capture dispatch + return within try/finally or synchronous boundary.
5. **Opt-in ledger**: `pipeline.py` writes to ledger only when `workspace` is provided; graceful no-op if missing.

## Unsupported in Spec-002

- Cancellation, retry, timeout management (ledger records status only).
- Budget reservation, approval gates, policy decisions (policy.py present but not invoked on dispatch).
- Typed message envelopes, versioned schemas.
- Replay detection, deduplication, cryptographic binding.
- Remote dispatch, MCP protocols, tool use (adapters suppress tools; claude/codex via CLI only).

Spec-003 governance slice will add these constraints.
