# Decisions — 2026-09-05 planning session

CEO (Dom) rulings from grill session with fable (CTO) + astra (CSO). Each supersedes PLAN-MVP where they conflict. PLAN-MVP rewrite pending.

| # | Decision | Supersedes in PLAN-MVP |
|---|---|---|
| D1 | Free = zero $ + free-tier API keys OK | §1 DEFERRED "API-key tooling" |
| D2 | Setup walks non-coder through key acquisition and writes user `.env`; agent never sees a key; key never enters any model prompt | new |
| D3 | Hosts at launch: Claude Code AND Codex, from one canonical skill source | confirms §5 |
| D4 | Acceptance users day 1: Tim (docs to cited brief) AND Dom (eng/sci) | §4 default-lawyer-only proof |
| D5 | Metric: $/accepted task, quality floor 0 false-accepts on seeded faults, baseline all-frontier | new |
| D6 | Providers: Claude+Codex required; Gemini/Mistral/OpenRouter optional; missing key skips, never blocks | §1 DEFERRED Gemini/Mistral/OR |
| D7 | Confidential inputs to optional providers: deny until explicit per-workspace authorization. Future: deterministic synthetic redaction (far out) | extends §4 safety |
| D8 | START-HERE: caveman-lite + nested-notes first draft, then write-like-scientist pass; human-skimmable, no AI slop | open question closed |
| D9 | Spend cap: hard $0/task; quota out = pause + tell user; no paid API | new |
| D10 | No savings % promised until measured on both workflows | new |
| D11 | Key UX: agent opens browser to provider key page; key typed into hidden local terminal prompt; never chat | new |
| D12 | Distribution: marketplace where supported + git URL fallback | §6 capsule-first |

## Consequences flagged by astra (S1, S2)
- Default Tim path (no free keys, no workspace auth) routes only through Claude+Codex subscriptions. Dollar savings there are quota savings, not cash. Report incremental $ and subscription allocation separately.
- Zero-dollar baseline means no percentage claim; publish measured $/accepted task only.

## Self-decidable (no CEO input), owned by CTO
- Model-to-tier assignment: probe + benchmark, not chosen by name (astra M0-M6 draft in session scratchpad).
- Memory backend after host/runtime probe.
- `--bare` OAuth probe against logged-in CLI.
- `agent_runner.py:248` exit0 to `returned`; `verified` requires gates.

## Next
1. Rewrite PLAN-MVP §1, §5, §6 against D1-D12 (astra, then fable verifies).
2. ADRs for D9 (hard $0 cap) and D7 (deny-by-default): hard to reverse, surprising, real trade-off.
3. Then Phase 1 build only on CEO "build".

## Probes (2026-09-05)
- `--bare` OAuth claim VERIFIED on claude 2.1.261: `claude --bare -p` returns "Not logged in"; `claude -p` succeeds. Adapter must exclude `--bare`; isolate via `--setting-sources`, `--tools`, `--strict-mcp-config` (to be tested).
- Tool isolation probe (haiku, `-p --disallowedTools <all> --setting-sources "" --strict-mcp-config`): shell request answered `NO_EXEC`. `--tools ""` alone did NOT suppress tool list. Adapter uses explicit `--disallowedTools` list. One positive probe only; negative-probe matrix still needed in Phase 1.
- Verifier weakness found by fixture test (2026-09-05): whitespace-normalized substring match accepts negation-prefix forgeries (`signed 16-bit` ⊂ `unsigned 16-bit`). Phase 1 fixture adjusted; Phase 3 verifier must add word-boundary matching. Tracked as a seeded-fault class for the release gate.
- Phase 1 real-CLI probe (claude haiku, tool-free, 2026-09-05): `tim needs-review checked 5 matched 5 fails []`; `dom needs-review checked 5 matched 5 fails []`. Two defects found and fixed en route: `--disallowedTools` variadic swallowed positional prompt (prompt now on stdin, `--` terminator); worker fenced JSON + miscounted paragraphs (fence strip + `[pN]` numbering in prompt). Open: haiku returned empty `draft` on both runs. Codex probe blocked by quota until 13:07 (D9 pause observed live).
- Codex model IDs (2026-09-05): ChatGPT-account Codex rejects `gpt-5-mini`, `gpt-5`, `gpt-5-codex`, `o4-mini` ("not supported when using Codex with a ChatGPT account"). Supported (PONG): `gpt-5.4-mini` (cheap), `gpt-5.6-luna` (mid), `gpt-6-astra` (frontier). routing.json updated.
- Phase 1 end-to-end, both required providers, tim fixture: `tim/haiku needs-review 5/5`, `tim/codex gpt-5.4-mini needs-review 5/5`. Both drafts cite (pN) and surface the Clause 3 vs Clause 8 conflict unprompted. Draft-missing now downgrades to `returned`.

## Astra drift check on Phase 1 @ bd33f7e (2026-09-05)
- CONFLICT (fixed same day): zero claims passed the Verifier trivially → false accept vs D5; draft citations unchecked. Fix: `passed` requires ≥1 claim; word-boundary quote match; every `(pN)` in draft must map to a claim anchor.
- CONFLICT (Phase 2): Codex `-s read-only` still permits shell reads; Worker glossary says no tools → needs a stricter Codex isolation config + negative probes on both adapters.
- CONFLICT (Phase 2): `available_providers()` assumes both logins present; Phase 2 doctor must probe each CLI and block on missing Required provider.
- RISK (Phase 2): routing always prefers Claude; Tim with only Codex working stalls. Router should skip providers whose probe failed.
- NEXT (astra, accepted as Phase 2 order): acceptance gate hardening + other-vendor Reviewer → execution boundary (isolation, login preflight, quota, hidden-key UX) → measured Tim+Dom pilot vs all-frontier.

## Phase 2 probes (2026-09-05)
- Isolation, claude worker (`-p --disallowedTools <all> --setting-sources "" --strict-mcp-config`): host-file read CLEAN, cwd listing CLEAN, web fetch CLEAN.
- Isolation, codex worker: with `-s read-only -C <empty> shell_environment_policy.inherit="none" tools.web_search=false` → host-file read LEAK, web fetch LEAK. Fixed by `-c features.shell_tool=false` + `-c web_search="disabled"` (string; `tools.web_search=false` is ignored, `web_search=false` errors). After fix: 3/3 CLEAN. `-s read-only` alone is NOT isolation.
- Reviewer, real run, tim: worker haiku 5/5 quotes → reviewer gpt-5.6-luna returned `issues`: claim 1 qualified by Clause 8; 2 omissions. Status needs-review (correct: draft did not name the clause conflict). `verified` not yet observed on a real run; that is the gate working, not a bug.
- Bench N=1 (2026-09-05, `docs/BENCH.md`): cheap pipeline (haiku or gpt-5.4-mini worker + other-vendor luna/sonnet reviewer) → 4/4 accepted at `needs-review`, 5/5 quotes each, 20–30 s. Frontier single-model baseline (fable, gpt-6-astra) → 4/4 verifier pass, 10–16 s. Reviewer flagged real qualification issues on every cheap run; `verified` not yet reached on real runs. Incremental $ = 0 all configs (D9). No % claim (D10, N<5). Observation: cheap path costs 2 subscription calls vs 1 and ~2× wall-clock, buys an independent review the baseline lacks.
- Bench defects fixed same day: router preferred Claude so "codex/cheap" ran haiku (added `prefer_provider`); frontier baseline could never be "accepted" under the reviewer rule (baseline now = verifier pass, stated in the table).
- Delegate honesty note: one haiku dispatch reported a 2-line fix it had not written; caught by re-reading the file. Supervisor applied the swap directly (policy deviation, logged).

## therapy_copi fan-out failure — diagnosed by Opus 5 (2026-09-05)
- Root cause: two parallel systems. New `workerbees/` has adapters for claude+codex only; Gemini/Mistral/OpenRouter live as legacy shell wrappers `skills/codex-bridge/scripts/{gask,mask,oask}.sh` with per-provider key files (`~/.codex-bridge/gemini-key`, `~/.config/devstral/api_key`, `~/.codex-bridge/openrouter-key`). Session searched for python adapters + `~/.config/workerbees/.env`, found neither, concluded "never built". No doc heading pointed at the wrappers.
- Wrapper status: gemini LIVE (PONG); mistral key EXPIRED 2026-09-04; openrouter key file is a stub → both need rotation by operator.
- Fixes: HOW-IT-WORKS `## Legacy wrappers for optional providers`; SKILL.md pointer; routing.json `optional_provider_wrappers`. No new adapters (Phase 3 decision).
- Correction: commit cc8f811's message claims the invalid-reviewer/verifier_pass fix; Opus's cleanup reverted those edits before the commit. Re-applied in the following commit.

## D13 candidate — dispatch graph (CEO idea 2026-09-05, not yet ruled)
- Idea: every fan-out emits a graph (node = job w/ model, tier, task, parent; edges = depends-on / reviews / corrects) to make hierarchy and tokenomics deterministic and auditable.
- CTO position: adopt as a ledger emitted by the runner (agent_runner already stores parent_id in SQLite), linted by rules (depth ≤1, reviewer = other-vendor sibling, frontier nodes need a gate reason, subtree cost rollup). NOT an LLM-planned graph per spawn (frontier spend to save cheap spend).
- First step: receipts carry `parent_id` + `edge` so the graph is derivable; visualization later.

## Phase 3 probes (2026-09-05)
- First real `verified`: tim, worker haiku (5/5 quotes, every sentence cited), reviewer gpt-5.6-luna → all verdicts ok, 0 omissions, 0 corrections. Draft names the Clause 3→8 override explicitly. Per-assertion draft check + omission-aware review prompt changed the outcome vs Phase 2 (which stopped at needs-review). N=1; not a quality claim.
- Phase 3 T2 (correction loop) written by Codex gpt-5.4-mini, reviewed by gpt-5.6-luna (OpenAI-first per CEO, usage rebalancing); 73 tests.
- speckit analyze (sonnet) produced 2 false CRITICAL/HIGH findings (claimed pipeline.py missing while a Codex worker was editing it). Lesson: analyze must not run concurrently with a writer on the same files; supervisor verified on disk before acting.

## Ledger MVP

Dispatch graph ledger records all delegated jobs (worker, reviewer, correction, doctor probe) as nodes with edges. MVP scope: User Story 1 (Audit who did what). Acceptance test (SC-001): brief with worker + reviewer produces 2 nodes + 1 "reviews" edge; lint rules (depth, same_vendor_review, frontier_without_gate) detect violations deterministically; JSON round-trip preserves all fields; cost rollup computes per-root subtree sums. All 97 tests pass (75 prior + 22 ledger). Ledger failure never affects brief status (FR-008, SC-004). Run-id groups nodes per brief; run_id dedup on load prevents cross-brief interleaving.
- Ledger real run (dom, haiku worker + luna reviewer): 2 nodes, 1 `reviews` edge, Mermaid + rollup rendered, lint clean, `ledger_error` None. Reviewer returned `paused` (Codex quota exhausted mid-run) → status `paused`, recorded. OpenAI usage deliberately exhausted first per CEO; astra governance assessment deferred to quota reset.
- CEO question, graph algorithms for tokenomics: CTO answer = optimize on ledger-derived edge weights (calls/accepted), enforce legality on governance graph; MVP order topo/cycle → empirical edge weights → constrained shortest path → critical path; min-cost-flow/bandits overkill until multi-worker decomposition exists. Astra to second-opinion (§8 of its brief).
