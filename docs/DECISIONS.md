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
