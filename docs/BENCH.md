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
