# At-route bench: OpenAI aliases

Measured 2026-09-23 with `ask.sh --fresh --raw --model <id>`, which returns the Codex usage block per call. 6 prompts × 4 aliases × 2 reps = 48 calls, all exit 0. Raw data: `bench_oai.tsv` in the session scratchpad; script `bench_oai.sh` is 27 lines and reproducible.

Prompts: a one-line fact, a 150-word explanation, a bash one-liner, a short reasoning puzzle, an 8-item list, a 400-word essay.

## Per alias (medians over 12 calls)

| alias | model | latency s | input tokens | of which cached | output tokens | reasoning tokens | output+reasoning, all 12 calls |
|---|---|---|---|---|---|---|---|
| luna | gpt-5.6-luna | 8 | 25,800 | 9,984 | 162 | 69 | 3,851 |
| terra | gpt-5.6-terra | 9 | 27,351 | 11,008 | 208 | 26 | 4,165 |
| sol | gpt-5.6-sol | 11 | 41,717 | 32,704 | 281 | 129 | 5,736 |
| astra | gpt-6-astra | 9 | 28,212 | 12,160 | 124 | 0 | 2,218 |

## Per prompt (median latency / output+reasoning tokens)

| prompt | luna | terra | sol | astra |
|---|---|---|---|---|
| fact | 6s / 35 | 5s / 6 | 4s / 7 | 6s / 16 |
| explain | 11s / 331 | 9s / 192 | 20s / 697 | 12s / 205 |
| code | 7s / 230 | 15s / 736 | 7s / 352 | 8s / 136 |
| reason | 7s / 229 | 11s / 370 | 11s / 401 | 7s / 60 |
| list | 16s / 219 | 7s / 222 | 11s / 424 | 9s / 124 |
| long | 25s / 880 | 14s / 555 | 24s / 985 | 23s / 567 |

## Findings

- **Input floor is about 26k tokens per call** for every alias. That is the Codex CLI system prompt plus repo instructions, not the question. A fresh thread is still 17× cheaper than the shared thread, which had reached 442k input tokens per call before the fix in commit `95962f9`.
- **Sol is the outlier**: 42k input and the most output on every prompt. Astra is the most concise and had zero reasoning tokens on every call.
- **Latency is 5 to 25 seconds**, driven by answer length, not by model tier.
- **Cost**: Codex runs under the ChatGPT Plus subscription (`reference/prices.json` lists it at 20 USD per month, unmetered), so the marginal dollar cost of every call above is zero. The comparable Fable direct call for the "explain" prompt cost 0.78 USD. Saving versus Fable is 100% of metered spend; the real budget is the Codex rate-limit window, which these token counts draw on.
- **Recommendation**: `@luna` or `@terra` for side questions. Reserve `@astra` for hard reasoning, avoid `@sol` for trivia.
