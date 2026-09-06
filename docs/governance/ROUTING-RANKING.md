# Routing ranking (CEO, 2026-09-06)

Working routing ranking, not a universal benchmark ranking. 1 = best fit for that task; lower-ranked models may still be preferable when cost, speed, or tool compatibility matters.

| Model | Hard reasoning | Complex coding | Agentic/tool use | Research & long context | Writing & analysis | Document extraction | Routine coding | Classification / summarization | Speed / cost |
|---|---|---|---|---|---|---|---|---|---|
| Claude Fable 5 | 1 | 1 | 2 | 1 | 1 | 1 | 4 | 4 | 8 |
| GPT-6 Astra | 2 | 2 | 1 | 2 | 4 | 3 | 5 | 5 | 7 |
| GPT-5.6 Sol | 3 | 3 | 3 | 4 | 5 | 5 | 1 | 3 | 6 |
| Claude Opus 5 | 4 | 4 | 4 | 3 | 2 | 4 | 3 | 4 | 5 |
| Claude Sonnet 5 | 5 | 5 | 6 | 5 | 3 | 2 | 2 | 2 | 3 |
| GPT-5.6 Terra | 6 | 6 | 5 | 6 | 6 | 6 | 2 | 1 | 2 |
| Claude Haiku 4.5 | 7 | 8 | 8 | 7 | 7 | 6 | 6 | 1 | 1 |
| GPT-5.6 Luna | 8 | 7 | 7 | 8 | 8 | 7 | 5 | 2 | 1 |

## Rungs

| Rung | Default | Escalate to | Second opinion when |
|---|---|---|---|
| Supervisor | Fable 5 or Astra | the other frontier model | final decisions, conflicting results, high-risk actions |
| Orchestrator | Opus 5 or Sol | Fable 5 or Astra | task decomposition ambiguous, dependencies complex |
| Workhorse | Sonnet 5 or Terra | Opus 5 or Sol | coding, research, or synthesis has meaningful uncertainty |
| Grunt | Haiku 4.5 or Luna | the other cheap model | outputs anomalous or validation cheap |

## Routing rule

```text
if irreversible, high-risk, or strategically important:  Fable 5 <-> Astra
elif complex planning, coding, or multi-step delegation:  Opus 5 <-> Sol
elif normal research, coding, synthesis, or document work: Sonnet 5 <-> Terra
else:                                                      Haiku 4.5 <-> Luna
```

Second opinion: send the task to the paired model without showing the first answer. A Supervisor compares both outputs afterward.

Source: CEO message, 2026-09-06, citing openai.com positioning of Astra as frontier tier and GPT-5.6 as a family spanning capability and efficiency.
