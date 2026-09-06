# Bench: measured pilot (D5/D10)

| fixture | provider/tier | model | status | quotes | reviewer | review | seconds | accepted | verifier_pass |
|---|---|---|---|---|---|---|---|---|---|
| tim | claude/cheap | haiku | needs-review | 5/5 | issues | issues | 20.4 | True | True |
| tim | codex/cheap | gpt-5.4-mini | needs-review | 5/5 | issues | issues | 27.6 | True | True |
| tim | claude/frontier | fable | returned | 5/5 | disabled | disabled | 10.7 | False | True |
| tim | codex/frontier | gpt-6-astra | returned | 5/5 | disabled | disabled | 14.2 | False | True |
| dom | claude/cheap | haiku | needs-review | 5/5 | issues | issues | 27.6 | True | True |
| dom | codex/cheap | gpt-5.4-mini | needs-review | 5/5 | issues | issues | 29.5 | True | True |
| dom | claude/frontier | fable | returned | 5/5 | disabled | disabled | 10.6 | False | True |
| dom | codex/frontier | gpt-6-astra | returned | 5/5 | disabled | disabled | 15.8 | False | True |

- Frontier baseline
  - **Reviewer**
    - Frontier baseline runs without a Reviewer, so it cannot reach accepted.
  - **Comparison**
    - Compare frontier runs on verifier_pass and seconds.

## Per configuration

- Results
  - **claude/cheap**
    - accepted 2/2. verifier_pass 2/2. Mean seconds 24.0. Incremental dollars: 0 (subscription only, D9). Subscription calls: 4
  - **codex/cheap**
    - accepted 2/2. verifier_pass 2/2. Mean seconds 28.6. Incremental dollars: 0 (subscription only, D9). Subscription calls: 4
  - **claude/frontier**
    - accepted 0/2. verifier_pass 2/2. Mean seconds 10.6. Incremental dollars: 0 (subscription only, D9). Subscription calls: 2
  - **codex/frontier**
    - accepted 0/2. verifier_pass 2/2. Mean seconds 15.0. Incremental dollars: 0 (subscription only, D9). Subscription calls: 2
- Savings
  - **Reporting rule**
    - Report no savings percentage until both workflows reach N≥5 (D10).

```json
[
 {
  "fixture": "tim",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "needs-review",
  "checked": 5,
  "matched": 5,
  "reviewer": "issues",
  "seconds": 20.4,
  "accepted": true,
  "review": "issues",
  "verifier_pass": true
 },
 {
  "fixture": "tim",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "needs-review",
  "checked": 5,
  "matched": 5,
  "reviewer": "issues",
  "seconds": 27.6,
  "accepted": true,
  "review": "issues",
  "verifier_pass": true
 },
 {
  "fixture": "tim",
  "provider": "claude",
  "tier": "frontier",
  "model": "fable",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "disabled",
  "seconds": 10.7,
  "accepted": false,
  "review": "disabled",
  "verifier_pass": true
 },
 {
  "fixture": "tim",
  "provider": "codex",
  "tier": "frontier",
  "model": "gpt-6-astra",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "disabled",
  "seconds": 14.2,
  "accepted": false,
  "review": "disabled",
  "verifier_pass": true
 },
 {
  "fixture": "dom",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "needs-review",
  "checked": 5,
  "matched": 5,
  "reviewer": "issues",
  "seconds": 27.6,
  "accepted": true,
  "review": "issues",
  "verifier_pass": true
 },
 {
  "fixture": "dom",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "needs-review",
  "checked": 5,
  "matched": 5,
  "reviewer": "issues",
  "seconds": 29.5,
  "accepted": true,
  "review": "issues",
  "verifier_pass": true
 },
 {
  "fixture": "dom",
  "provider": "claude",
  "tier": "frontier",
  "model": "fable",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "disabled",
  "seconds": 10.6,
  "accepted": false,
  "review": "disabled",
  "verifier_pass": true
 },
 {
  "fixture": "dom",
  "provider": "codex",
  "tier": "frontier",
  "model": "gpt-6-astra",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "disabled",
  "seconds": 15.8,
  "accepted": false,
  "review": "disabled",
  "verifier_pass": true
 }
]
```

## OpenRouter catalog probe — 2026-09-06

- Method: one `/bin/zsh oask.sh` call per catalog route. Fixed response contract: `PONG`, then `POSITIVE` for a fixed positive sentence.
- Result: 0 `probed_ok`; 17 `probed_fail`; 6 `quota`. Runtime detail is retained in `.workerbees/model_probes.json`.
- Interpretation: this is an availability result, not a model-quality ranking. Empty completions, route restrictions, retired routes, and the hard `:free` guard remain visible.

| Model | Status | Seconds | Result |
|---|---:|---:|---|
| `cohere/north-mini-code:free` | probed_fail | 1.025 | Empty completion |
| `dots-studio/dots-3-note-preview:free` | probed_fail | 3.573 | Empty completion |
| `google/gemma-4-26b-a4b-it:free` | quota | 0.504 | HTTP 429 daily free limit |
| `google/gemma-4-31b-it:free` | quota | 0.380 | HTTP 429 daily free limit |
| `google/lyria-3-clip-preview` | probed_fail | 0.012 | Refused: not `:free` |
| `google/lyria-3-pro-preview` | probed_fail | 0.012 | Refused: not `:free` |
| `inclusionai/ling-3.0-flash-fin:free` | probed_fail | 2.045 | Empty completion |
| `inclusionai/ling-3.0-flash-sante:free` | probed_fail | 3.043 | Empty completion |
| `liquid/lfm-2.5-2.6b:free` | probed_fail | 2.298 | Empty completion |
| `minimax/minimax-m2.7:free` | probed_fail | 5.613 | Empty completion |
| `minimax/minimax-m3:free` | probed_fail | 1.359 | Empty completion |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | quota | 0.310 | HTTP 429 daily free limit |
| `nvidia/nemotron-3-super-120b-a12b:free` | quota | 0.406 | HTTP 429 daily free limit |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | probed_fail | 83.117 | Empty completion |
| `nvidia/nemotron-3.5-content-safety:free` | probed_fail | 2.613 | Empty completion |
| `nvidia/nemotron-3.5-lightning:free` | probed_fail | 10.270 | Empty completion |
| `openrouter/auto:free` | probed_fail | 0.284 | HTTP 404; no route matched restrictions |
| `openrouter/free` | probed_fail | 0.013 | Refused: not `:free` suffix |
| `poolside/laguna-s-2.1:free` | quota | 0.552 | HTTP 429 provider limit |
| `poolside/laguna-xs-2.1:free` | quota | 0.429 | HTTP 429 provider limit |
| `thinkingmachines/inkling-small:free` | probed_fail | 0.159 | HTTP 403; agentic harness required |
| `thinkingmachines/inkling:free` | probed_fail | 0.168 | HTTP 403; agentic harness required |
| `z-ai/glm-5.2:free` | probed_fail | 0.170 | HTTP 404; free route unavailable |


## T15 governance benchmark — 2026-09-06

**Reading of record (fable, 2026-09-06):** 40 rows ran end to end (5 repeats × Tim/Dom × haiku/gpt-5.4-mini × off/enforce), 59 wrapper-observed calls.

- Status parity off vs enforce: 20/20 pairs identical. Governance changed no outcome.
- Gate line below reads FAIL because no row reached `verified` or `needs-review`: every Codex call returned "You've hit your usage limit" (Codex subscription quota exhausted at run time). Codex worker rows paused; haiku worker rows returned but their Codex reviewer paused.
- Conclusion: governance parity PASS; quality gate NOT MEASURED. Rerun after Codex quota reset.
- First run crashed before any row: pipeline off-mode reviewer call omitted `governance_mode`, so the reviewer fell back to `WORKERBEES_GOVERNANCE=enforce` from the env with no gateway. Fixed in this commit with a regression test.

Gate verified/needs-review unchanged vs governance=off: FAIL.

### Results

| fixture | governance | provider/tier | model | status | quotes | reviewer | review | seconds | accepted | verifier_pass |
|---|---|---|---|---|---|---|---|---|---|---|
| tim | off | claude/cheap | haiku | returned | 5/5 | paused | paused | 13.8 | False | True |
| tim | enforce | claude/cheap | haiku | returned | 5/5 | paused | paused | 14.1 | False | True |
| tim | off | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.0 | False | False |
| tim | enforce | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.6 | False | False |
| dom | off | claude/cheap | haiku | returned | 5/5 | paused | paused | 19.6 | False | True |
| dom | enforce | claude/cheap | haiku | returned | 5/5 | paused | paused | 14.1 | False | True |
| dom | off | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.1 | False | False |
| dom | enforce | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.7 | False | False |
| tim | off | claude/cheap | haiku | returned | 5/5 | paused | paused | 26.0 | False | True |
| tim | enforce | claude/cheap | haiku | returned | 5/5 | paused | paused | 18.3 | False | True |
| tim | off | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 3.3 | False | False |
| tim | enforce | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.1 | False | False |
| dom | off | claude/cheap | haiku | returned | 5/5 | paused | paused | 15.7 | False | True |
| dom | enforce | claude/cheap | haiku | returned | 5/5 | paused | paused | 15.0 | False | True |
| dom | off | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.6 | False | False |
| dom | enforce | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.9 | False | False |
| tim | off | claude/cheap | haiku | returned | 5/5 | paused | paused | 27.6 | False | True |
| tim | enforce | claude/cheap | haiku | returned | 5/5 | paused | paused | 18.2 | False | True |
| tim | off | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.7 | False | False |
| tim | enforce | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.6 | False | False |
| dom | off | claude/cheap | haiku | returned | 5/5 | paused | paused | 17.1 | False | True |
| dom | enforce | claude/cheap | haiku | returned | 5/5 | disabled | uncited_draft | 13.3 | False | True |
| dom | off | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.3 | False | False |
| dom | enforce | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.1 | False | False |
| tim | off | claude/cheap | haiku | returned | 5/5 | paused | paused | 17.9 | False | True |
| tim | enforce | claude/cheap | haiku | returned | 5/5 | paused | paused | 17.2 | False | True |
| tim | off | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.6 | False | False |
| tim | enforce | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.8 | False | False |
| dom | off | claude/cheap | haiku | returned | 5/5 | paused | paused | 15.5 | False | True |
| dom | enforce | claude/cheap | haiku | returned | 5/5 | paused | paused | 12.0 | False | True |
| dom | off | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.2 | False | False |
| dom | enforce | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.4 | False | False |
| tim | off | claude/cheap | haiku | returned | 5/5 | paused | paused | 14.8 | False | True |
| tim | enforce | claude/cheap | haiku | returned | 5/5 | paused | paused | 13.7 | False | True |
| tim | off | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.7 | False | False |
| tim | enforce | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.4 | False | False |
| dom | off | claude/cheap | haiku | returned | 5/5 | paused | paused | 14.1 | False | True |
| dom | enforce | claude/cheap | haiku | returned | 5/5 | paused | paused | 16.3 | False | True |
| dom | off | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.2 | False | False |
| dom | enforce | codex/cheap | gpt-5.4-mini | paused | None/None | disabled | None | 2.2 | False | False |

Frontier baseline runs without a Reviewer, so it cannot reach accepted; compare on verifier_pass and seconds.

## Per configuration
- claude/cheap (off): accepted 0/10; verifier_pass 10/10; mean seconds 18.2; statuses: {returned: 10}; corrections_mean: 0.0; incremental cost: unknown (subscription billing not measured); observed subscription calls: 20
- claude/cheap (enforce): accepted 0/10; verifier_pass 10/10; mean seconds 15.2; statuses: {returned: 10}; corrections_mean: 0.0; incremental cost: unknown (subscription billing not measured); observed subscription calls: 19
- codex/cheap (off): accepted 0/10; verifier_pass 0/10; mean seconds 2.5; statuses: {paused: 10}; corrections_mean: 0.0; incremental cost: unknown (subscription billing not measured); observed subscription calls: 10
- codex/cheap (enforce): accepted 0/10; verifier_pass 0/10; mean seconds 2.5; statuses: {paused: 10}; corrections_mean: 0.0; incremental cost: unknown (subscription billing not measured); observed subscription calls: 10

No savings percentage is reported until both workflows are measured at N≥5 (D10).

OpenRouter lane skipped: daily quota exhausted. Cost: subscription, unknown $. Calls are wrapper-observed, not estimated.

```json
[
 {
  "fixture": "tim",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 13.8,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 14.1,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.0,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.6,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 19.6,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 14.1,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.1,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.7,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 26.0,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 18.3,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 3.3,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.1,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 15.7,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 15.0,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.6,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.9,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 27.6,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 18.2,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.7,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.6,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 17.1,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "disabled",
  "seconds": 13.3,
  "accepted": false,
  "verifier_pass": true,
  "review": "uncited_draft",
  "corrections": 0,
  "paused_reason": null,
  "governance": "enforce",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.3,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.1,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 17.9,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 17.2,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.6,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.8,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 15.5,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 12.0,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.2,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.4,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 14.8,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 13.7,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.7,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "tim",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.4,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": " after the first twelve months.\n\n[p6] Clause 15. Landlord is not liable for water damage except where caused by Landlord negligence.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 14.1,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "claude",
  "tier": "cheap",
  "model": "haiku",
  "status": "returned",
  "checked": 5,
  "matched": 5,
  "reviewer": "paused",
  "seconds": 16.3,
  "accepted": false,
  "verifier_pass": true,
  "review": "paused",
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 2,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.2,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "off",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 },
 {
  "fixture": "dom",
  "provider": "codex",
  "tier": "cheap",
  "model": "gpt-5.4-mini",
  "status": "paused",
  "checked": null,
  "matched": null,
  "reviewer": "disabled",
  "seconds": 2.2,
  "accepted": false,
  "verifier_pass": false,
  "review": null,
  "corrections": 0,
  "paused_reason": "ified against site data.\n\n[p6] Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.\n\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\nERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 6:04 PM.\n",
  "governance": "enforce",
  "subscription_calls": 1,
  "incremental_cost": "subscription, unknown $"
 }
]
```
