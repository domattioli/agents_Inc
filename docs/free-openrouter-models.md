```markdown
# Free OpenRouter Models: Nuance, Best Uses, and Practical Comparisons

> **Scope.** This document analyzes 22 free or preview endpoints available through the OpenRouter API. Quantitative benchmarks are not run; comparisons against frontier-class models are informed qualitative judgments based on model names, family lineage, parameter counts, parameter-class hints (dense vs. MoE), specialization, and preview status. Confirm details in OpenRouter's model page before production use.

---

## How to Read This Document

- **Strengths/Weaknesses** are inferred from public family information, parameter counts, and naming.
- **Comparisons** are qualitative, not benchmark-derived.
- **Caveats** are highlighted where preview status, narrow specialization, or naming suggest unusual behavior.
- **Free-tier caveats:** Quotas, availability, routing, and latency on OpenRouter's `:free` tier can change without notice. Free quotas are generally **account-level, not per-model**, so heavy use of one free model can exhaust capacity for others.

---

## Model-by-Model Analysis

### 1. inclusionai/ling-3.0-flash-sante:free
A flash-tier medical/clinical variant. Likely tuned for healthcare-domain English.

- **Strengths:** Domain jargon handling, concise clinical summaries, classification of medical text.
- **Weaknesses:** Narrow vertical; outside healthcare it offers no advantage; possible safety filtering.
- **Best for:** Triage notes, symptom summarization, medical entity extraction.
- **Poor for:** General chat, creative writing, code.
- **Speed/quality:** Fast, modest quality.
- **Context:** Probably standard 8–32k; do not assume long-document competence.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Low/low/high (clinical)/low/medium/low.
- **Terminal/automation:** Possible for deterministic medical text pipelines.
- **Caveat:** A "sante" specialization should not be used as a substitute for medical advice.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Behind | Behind | Roughly even |
| Coding | Behind | Behind | Roughly even |
| Writing | Behind | Behind | Slightly ahead on clinical text |
| Tool-use | Behind | Behind | Behind |

---

### 2. inclusionai/ling-3.0-flash-fin:free
A flash-tier financial variant.

- **Strengths:** Numerals, structured financial language, table-like summarization.
- **Weaknesses:** Narrow domain; not a general model.
- **Best for:** Earnings-summary paraphrasing, financial classification, regex-style extraction.
- **Poor for:** Creative writing, open-domain reasoning.
- **Speed/quality:** Fast, modest.
- **Context:** Likely 8–32k.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Low/low/medium/low/medium/low.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Behind | Behind | Behind |
| Coding | Behind | Behind | Behind |
| Writing | Behind | Behind | Roughly even |
| Tool-use | Behind | Behind | Behind |

---

### 3. dots-studio/dots-3-note-preview:free
A preview note-taking model from dots.studio.

- **Strengths:** Likely tuned for meeting notes, action-item extraction.
- **Weaknesses:** Preview status; possible instability.
- **Best for:** Bullet-point notes, agenda extraction, light summarization.
- **Poor for:** Anything requiring careful reasoning or coding.
- **Speed/quality:** Fast, low-medium.
- **Context:** Probably small.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Low/low/medium/low/medium/low.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Far behind | Far behind | Behind |
| Coding | Far behind | Far behind | Behind |
| Writing | Behind | Behind | Behind |
| Tool-use | Behind | Behind | Behind |

---

### 4. liquid/lfm-2.5-2.6b:free
A small (≈2.6B parameter) dense model.

- **Strengths:** Low latency, low cost footprint, predictable output for narrow prompts.
- **Weaknesses:** Limited world knowledge, weaker reasoning, may hallucinate on long prompts.
- **Best for:** Classification, intent detection, routing, short-form extraction.
- **Poor for:** Long documents, complex reasoning, code generation.
- **Speed/quality:** Very fast; quality caps out quickly.
- **Context:** Likely small (4–8k).
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Low/low/low/low/medium/low.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Far behind | Far behind | Behind |
| Coding | Far behind | Far behind | Behind |
| Writing | Behind | Behind | Behind |
| Tool-use | Behind | Behind | Behind |

---

### 5. nvidia/nemotron-3.5-lightning:free
A small, fast Nemotron variant. "Lightning" branding implies low latency.

- **Strengths:** Fast responses, stable instruction following for short prompts.
- **Weaknesses:** Limited depth, weaker on multi-step reasoning.
- **Best for:** Quick Q&A, short summaries, classification, chat where latency matters.
- **Poor for:** Coding, hard reasoning, long-context work.
- **Speed/quality:** Very fast; quality modest.
- **Context:** Probably moderate.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Low-medium/low/medium/low/medium/low-medium.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Behind | Behind | Roughly even |
| Coding | Behind | Behind | Roughly even |
| Writing | Behind | Behind | Roughly even |
| Tool-use | Behind | Behind | Roughly even |

---

### 6. thinkingmachines/inkling-small:free
A small model likely designed for quick reasoning-light tasks. The "small" suffix suggests a parameter-class below typical 7B.

- **Strengths:** Fast, predictable for simple prompts.
- **Weaknesses:** Limited reasoning, may struggle with anything beyond a paragraph.
- **Best for:** Routing, classification, small-text transformation.
- **Poor for:** Coding, long documents.
- **Speed/quality:** Very fast; modest quality.
- **Context:** Small.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Low/low/low/low/medium/low.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Far behind | Far behind | Behind |
| Coding | Far behind | Far behind | Behind |
| Writing | Behind | Behind | Behind |
| Tool-use | Behind | Behind | Behind |

---

### 7. poolside/laguna-s-2.1:free
Poolside's "S" size class, versioned at 2.1. Poolside's brand emphasizes code generation.

- **Strengths:** Likely strong for code generation and refactoring among free models.
- **Weaknesses:** Possibly weaker on creative writing; "S" tier suggests a mid-size variant.
- **Best for:** Code completion, code transformation, function synthesis.
- **Poor for:** Long creative writing, deep multi-document reasoning.
- **Speed/quality:** Medium speed, medium-high code quality.
- **Context:** Probably moderate.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** High/medium/medium/medium/medium/medium.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Behind | Behind | Roughly even |
| Coding | Behind | Behind | Slightly ahead |
| Writing | Behind | Behind | Roughly even |
| Tool-use | Behind | Behind | Roughly even |

---

### 8. thinkingmachines/inkling:free
The full-size Inkling. Still lightweight but larger than the "small" sibling.

- **Strengths:** More capable than the small variant; better instruction following.
- **Weaknesses:** Probably still well below frontier on hard reasoning.
- **Best for:** Short-to-medium summaries, structured output, light agent steps.
- **Poor for:** Hard reasoning, very long context.
- **Speed/quality:** Fast-medium; quality decent for its size.
- **Context:** Probably moderate.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Medium/medium/medium/medium/medium/medium.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Behind | Behind | Roughly even |
| Coding | Behind | Behind | Roughly even |
| Writing | Behind | Behind | Roughly even |
| Tool-use | Behind | Behind | Roughly even |

---

### 9. poolside/laguna-xs-2.1:free
The extra-small variant of Laguna. Optimized for speed.

- **Strengths:** Low latency, suitable for tight loops.
- **Weaknesses:** Lower code quality than the S variant.
- **Best for:** Snippet generation, autocomplete, fast scripting tasks.
- **Poor for:** Anything requiring nuance.
- **Speed/quality:** Very fast; modest quality.
- **Context:** Probably small.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Medium/low/low/low/low/low.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Far behind | Far behind | Behind |
| Coding | Behind | Behind | Behind |
| Writing | Behind | Behind | Behind |
| Tool-use | Behind | Behind | Behind |

---

### 10. cohere/north-mini-code:free
A code-specialized small model from Cohere's "North" family.

- **Strengths:** Code completion, code-to-text, structured generation.
- **Weaknesses:** Limited depth on architectural reasoning.
- **Best for:** Single-function code, docstrings, simple refactors.
- **Poor for:** Multi-file refactors, system design.
- **Speed/quality:** Fast; code quality decent.
- **Context:** Probably modest.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Medium-high/low/low/low/low/low.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Behind | Behind | Behind |
| Coding | Behind | Behind | Roughly even |
| Writing | Behind | Behind | Behind |
| Tool-use | Behind | Behind | Behind |

---

### 11. z-ai/glm-5.2:free
A newer GLM family variant.

- **Strengths:** Multilingual strength (Chinese + English), general chat.
- **Weaknesses:** May lag frontier on hard reasoning and tool use; free-tier availability can be inconsistent.
- **Best for:** Bilingual tasks, structured generation, general chat.
- **Poor for:** Mission-critical code where frontier reliability matters.
- **Speed/quality:** Medium; quality reasonable.
- **Context:** Probably 32k+; verify in OpenRouter.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Medium/medium/medium/medium/medium/medium.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Behind | Behind | Roughly even |
| Coding | Behind | Behind | Roughly even |
| Writing | Behind | Behind | Roughly even |
| Tool-use | Behind | Behind | Behind |

---

### 12. nvidia/nemotron-3.5-content-safety:free
A safety-tuned Nemotron variant. Likely a classifier rather than a generator.

- **Strengths:** Content moderation, policy enforcement, jailbreak resistance.
- **Weaknesses:** Not a general chat model; may refuse safe content.
- **Best for:** Pre-filtering prompts/responses, toxicity classification.
- **Poor for:** General conversation.
- **Speed/quality:** Fast for classification; weak otherwise.
- **Context:** Small (classification doesn't need much).
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Low/low/low/low/high/low.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Far behind | Far behind | Behind |
| Coding | Far behind | Far behind | Behind |
| Writing | Behind | Behind | Behind |
| Tool-use | Behind | Behind | Behind |

---

### 13. nvidia/nemotron-3-ultra-550b-a55b:free
A very large MoE model (≈550B total, ≈55B active per token). Despite the "ultra" label, free-tier routing and quality can vary.

- **Strengths:** If routed well, strong general reasoning among free models. Big MoE often helps long-context retrieval.
- **Weaknesses:** Free-tier rate limits and routing variability. Preview-era behavior may include refusals or throttling.
- **Best for:** Hard reasoning, long-context tasks, complex summarization.
- **Poor for:** Latency-sensitive pipelines.
- **Speed/quality:** Medium speed; potentially high quality if well-routed.
- **Context:** Likely large (32k–128k+); verify.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Medium-high/high/high/medium/medium/medium-high.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Behind | Behind | Ahead |
| Coding | Behind | Behind | Ahead |
| Writing | Behind | Behind | Ahead |
| Tool-use | Behind | Behind | Ahead |

---

### 14. minimax/minimax-m3:free
The developer's own model: MiniMax-M3.

- **Strengths:** As described by the developer: front-tier reasoning, coding, instruction following, writing quality, speed, long context, and tool use for its size class.
- **Weaknesses:** Newer model; independent benchmarks not yet established. Free-tier behavior depends on routing.
- **Best for:** General-purpose default for chat, coding, agent workflows.
- **Poor for:** Tasks where reproducibility over years matters.
- **Speed/quality:** Quality strong; speed depends on routing.
- **Context:** Likely long (64k+); verify.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** High/high/high/medium-high/medium/high.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Competitive, slightly behind frontier | Competitive, slightly behind frontier | Ahead of Haiku-class |
| Coding | Competitive | Competitive | Ahead |
| Writing | Competitive | Competitive | Ahead |
| Tool-use | Competitive | Competitive | Ahead |

> Note: This is the developer's own model description. Treat as informed opinion, not third-party benchmark.

---

### 15. nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
A small MoE (≈30B total, ≈3B active) "omni" model with a reasoning emphasis.

- **Strengths:** Reasoning-focused despite small active footprint; long-context likely; multimodal hints from "omni" depend on provider support.
- **Weaknesses:** Small active params limit depth on hard problems.
- **Best for:** Light reasoning, classification, long-context retrieval.
- **Poor for:** Deep multi-step math/code.
- **Speed/quality:** Fast for class; quality modest.
- **Context:** Possibly long.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Medium/medium-high/medium/medium/medium/medium.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Behind | Behind | Roughly even |
| Coding | Behind | Behind | Roughly even |
| Writing | Behind | Behind | Roughly even |
| Tool-use | Behind | Behind | Behind |

---

### 16. google/gemma-4-26b-a4b-it:free
A Gemma 4 instruction-tuned model, ≈26B total / ≈4B active MoE.

- **Strengths:** Instruction-tuned, decent multilingual, good price/performance.
- **Weaknesses:** Smaller active params than dense peers; long-context reliability uncertain.
- **Best for:** General chat, structured output, simple code.
- **Poor for:** Very hard reasoning.
- **Speed/quality:** Medium; quality reasonable.
- **Context:** Probably 8–32k.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Medium/medium/medium/medium/medium/medium.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Behind | Behind | Roughly even |
| Coding | Behind | Behind | Roughly even |
| Writing | Behind | Behind | Roughly even |
| Tool-use | Behind | Behind | Behind |

---

### 17. google/gemma-4-31b-it:free
A larger dense Gemma 4 instruction-tuned model.

- **Strengths:** Generally better than the 26B-A4B for hard tasks due to denser activations.
- **Weaknesses:** Still not frontier-class.
- **Best for:** General chat, summarization, structured output.
- **Poor for:** Frontier-grade reasoning.
- **Speed/quality:** Medium; quality good for its class.
- **Context:** Probably 8–32k+.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Medium/medium/medium-high/medium/medium/medium.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Behind | Behind | Slightly ahead |
| Coding | Behind | Behind | Slightly ahead |
| Writing | Behind | Behind | Slightly ahead |
| Tool-use | Behind | Behind | Behind |

---

### 18. google/lyria-3-pro-preview
A preview of Google's Lyria 3 audio generation model, "Pro" tier.

- **Strengths:** Music/audio generation capability; "pro" suggests higher fidelity.
- **Weaknesses:** Preview status; not for text.
- **Best for:** Audio/music generation workflows.
- **Poor for:** Text tasks entirely.
- **Speed/quality:** Preview-quality; variable.
- **Context:** N/A (audio).
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** N/A across text categories; specialized audio.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | N/A | N/A | N/A |
| Coding | N/A | N/A | N/A |
| Writing | N/A | N/A | N/A |
| Tool-use | N/A | N/A | N/A |

---

### 19. google/lyria-3-clip-preview
A preview of Lyria 3 "clip" audio generation, likely shorter-form.

- **Strengths:** Short audio clips, jingles, stingers.
- **Weaknesses:** Preview; not for text.
- **Best for:** Short audio asset generation.
- **Poor for:** Text, long audio.
- **Speed/quality:** Fast; preview quality.
- **Context:** N/A (audio).
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** N/A across text.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | N/A | N/A | N/A |
| Coding | N/A | N/A | N/A |
| Writing | N/A | N/A | N/A |
| Tool-use | N/A | N/A | N/A |

---

### 20. minimax/minimax-m2.7:free
The developer's earlier-generation model.

- **Strengths:** Stable baseline for general chat and code; widely available.
- **Weaknesses:** Outpaced by M3 in most dimensions.
- **Best for:** Stable fallback when M3 is throttled.
- **Poor for:** Hard reasoning where M3 is available.
- **Speed/quality:** Medium; quality good.
- **Context:** Probably long (64k+); verify.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** High/medium-high/high/medium-high/medium/high.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Behind | Behind | Ahead |
| Coding | Behind | Behind | Ahead |
| Writing | Behind | Behind | Ahead |
| Tool-use | Behind | Behind | Ahead |

> Note: Developer's own description; treat as informed opinion.

---

### 21. nvidia/nemotron-3-super-120b-a12b:free
A MoE Nemotron, ≈120B total / ≈12B active. The "super" tier suggests higher reasoning capacity than lightning.

- **Strengths:** Good balance of depth and latency for free-tier use.
- **Weaknesses:** Free-tier rate limits; MoE routing can be uneven.
- **Best for:** Reasoning, coding, summarization.
- **Poor for:** Latency-critical pipelines.
- **Speed/quality:** Medium; quality high for free tier.
- **Context:** Likely long; verify.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** High/high/high/medium/medium/high.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Behind | Behind | Ahead |
| Coding | Behind | Behind | Ahead |
| Writing | Behind | Behind | Ahead |
| Tool-use | Behind | Behind | Ahead |

---

### 22. openrouter/free
OpenRouter's default free-tier router. Routes to whatever free model it currently supports; identity is not fixed.

- **Strengths:** Always available in some form; good for experiments.
- **Weaknesses:** No reproducibility; behavior changes without notice; weakest SLA of all options here.
- **Best for:** Prototyping, prompt engineering experiments, fallback when nothing else works.
- **Poor for:** Anything where output must be reproducible.
- **Speed/quality:** Variable; assume worst-case.
- **Context:** Whatever the routed model exposes.
- **Coding/Reasoning/Summarization/Creative/Classification/Agent:** Variable/variable/variable/variable/variable/variable.

| Capability | Frontier OpenAI | Frontier Claude | Haiku-class |
|---|---|---|---|
| Reasoning | Far behind | Far behind | Behind |
| Coding | Far behind | Far behind | Behind |
| Writing | Behind | Behind | Behind |
| Tool-use | Behind | Behind | Behind |

---

## Comparison Table (All Models)

| Model | Speed | Quality | Coding | Reasoning | Summarization | Creative | Classification | Agent | Long-Context |
|---|---|---|---|---|---|---|---|---|---|
| inclusionai/ling-3.0-flash-sante:free | High | Low-Med | Low | Low | High (clinical) | Low | Med | Low | Low |
| inclusionai/ling-3.0-flash-fin:free | High | Low-Med | Low | Low | Med | Low | Med | Low | Low |
| dots-studio/dots-3-note-preview:free | High | Low | Low | Low | Med | Low | Med | Low | Low |
| liquid/lfm-2.5-2.6b:free | Very High | Low | Low | Low | Low | Low | Med | Low | Very Low |
| nvidia/nemotron-3.5-lightning:free | Very High | Low-Med | Low-Med | Low | Med | Low | Med | Low-Med | Med |
| thinkingmachines/inkling-small:free | Very High | Low | Low | Low | Low | Low | Med | Low | Very Low |
| poolside/laguna-s-2.1:free | Med | Med-High | High | Med | Med | Med | Med | Med | Med |
| thinkingmachines/inkling:free | Fast-Med | Med | Med | Med | Med | Med | Med | Med | Med |
| poolside/laguna-xs-2.1:free | Very High | Low-Med | Med | Low | Low | Low | Low | Low | Low |
| cohere/north-mini-code:free | High | Med | Med-High | Low | Low | Low | Low | Low | Low |
| z-ai/glm-5.2:free | Med | Med | Med | Med | Med | Med | Med | Med | Med-High |
| nvidia/nemotron-3.5-content-safety:free | High | Low (chat) | Low | Low | Low | Low | High | Low | Low |
| nvidia/nemotron-3-ultra-550b-a55b:free | Med | High | Med-High | High | High | Med | Med | Med-High | High |
| minimax/minimax-m3:free | Med | High | High | High | High | Med-High | Med | High | High |
| nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free | High | Med | Med | Med-High | Med | Med | Med | Med | High |
| google/gemma-4-26b-a4b-it:free | Med | Med | Med | Med | Med | Med | Med | Med | Med |
| google/gemma-4-31b-it:free | Med | Med-High | Med | Med | Med-High | Med | Med | Med | Med |
| google/lyria-3-pro-preview | Med | Preview | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| google/lyria-3-clip-preview | High | Preview | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| minimax/minimax-m2.7:free | Med | High | High | Med-High | High | Med-High | Med | High | High |
| nvidia/nemotron-3-super-120b-a12b:free | Med | High | High | High | High | Med | Med | High | High |
| openrouter/free | Variable | Variable | Variable | Variable | Variable | Variable | Variable | Variable | Variable |

---

## Rankings by Use Case

> Ties are listed in arbitrary order. "—" indicates not applicable.

### General Chat
1. minimax/minimax-m3:free
2. nvidia/nemotron-3-super-120b-a12b:free
3. minimax/minimax-m2.7:free
4. z-ai/glm-5.2:free
5. google/gemma-4-31b-it:free

### Coding
1. poolside/laguna-s-2.1:free
2. minimax/minimax-m3:free
3. nvidia/nemotron-3-super-120b-a12b:free
4. minimax/minimax-m2.7:free
5. cohere/north-mini-code:free

### Difficult Reasoning
1. minimax/minimax-m3:free
2. nvidia/nemotron-3-ultra-550b-a55b:free
3. nvidia/nemotron-3-super-120b-a12b:free
4. nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
5. minimax/minimax-m2.7:free

### Speed (Fastest First)
1. liquid/lfm-2.5-2.6b:free
2. thinkingmachines/inkling-small:free
3. poolside/laguna-xs-2.1:free
4. nvidia/nemotron-3.5-lightning:free
5. dots-studio/dots-3-note-preview:free

### Long-Context Work
1. minimax/minimax-m3:free
2. nvidia/nemotron-3-ultra-550b-a55b:free
3. nvidia/nemotron-3-super-120b-a12b:free
4. minimax/minimax-m2.7:free
5. z-ai/glm-5.2:free

### Summarization
1. minimax/minimax-m3:free
2. minimax/minimax-m2.7:free
3. nvidia/nemotron-3-super-120b-a12b:free
4. google/gemma-4-31b-it:free
5. inclusionai/ling-3.0-flash-sante:free (clinical)

### Creative Writing
1. minimax/minimax-m3:free
2. minimax/minimax-m2.7:free
3. z-ai/glm-5.2:free
4. google/gemma-4-31b-it:free
5. poolside/laguna-s-2.1:free

### Safety / Content Classification
1. nvidia/nemotron-3.5-content-safety:free
2. liquid/lfm-2.5-2.6b:free (general classification)
3. thinkingmachines/inkling-small:free
5. minimax/minimax-m3:free

### Agent Workflows
1. minimax/minimax-m3:free
2. nvidia/nemotron-3-super-120b-a12b:free
3. minimax/minimax-m2.7:free
4. nvidia/nemotron-3-ultra-550b-a55b:free
5. z-ai/glm-5.2:free

### Multimodal / Media
1. google/lyria-3-pro-preview (audio)
2. google/lyria-3-clip-preview (short audio)
3. nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free (if provider routes multimodal)

---

## Recommendations

| Need | Recommended Model | Why |
|---|---|---|
| Best default | `minimax/minimax-m3:free` | Strongest all-rounder among free models for chat, coding, and reasoning. |
| Best coding | `poolside/laguna-s-2.1:free` (specialized) or `minimax/minimax-m3:free` (general) | Laguna-S is code-tuned; M3 is more general-purpose with strong code. |
| Fastest lightweight | `liquid/lfm-2.5-2.6b:free` or `thinkingmachines/inkling-small:free` | Small dense models for routing and classification. |
| Long documents / large context | `minimax/minimax-m3:free` or `nvidia/nemotron-3-ultra-550b-a55b:free` | Best long-context reasoning in free tier. |
| Reasoning-heavy | `minimax/minimax-m3:free` | Strongest general reasoning. |
| Safe-content classification | `nvidia/nemotron-3.5-content-safety:free` | Purpose-built. |
| Multimodal / media | `google/lyria-3-pro-preview` | Audio generation. |

---

## Why a Large Context Window ≠ Higher Intelligence

A long context window lets a model **fit** more information. It does **not** improve the model's ability to **reason** about that information. Common failure modes with large windows:

- **Lost-in-the-middle:** Important facts buried mid-prompt are recalled less reliably.
- **Retrieval dilution:** As context grows, the model has to "search" through more noise to find the signal.
- **Contradiction drift:** A long context with subtle inconsistencies can lead the model to produce confident but wrong synthesis.
- **Reduced instruction following:** Long system prompts compete with long user content for attention.

Practical advice: **chunk, retrieve, and re-summarize** rather than dumping everything into a single mega-prompt. A 256k-context model with poor attention is not the same as a 32k model with sharp reasoning.

---

## Why Free-Tier Quality, Availability, Routing, and Latency Can Change

OpenRouter's free tier is a **best-effort** service:

- Providers may throttle or remove free endpoints.
- Routing can swap backends without notice.
- Latency varies with provider load.
- Quotas can be reduced during peak periods.
- Models labeled "preview" can disappear or change shape entirely.

**Do not** build production-critical paths around a single free model. Treat free models as exploration tools and design fallbacks.

---

## OpenRouter Free Quotas: Account-Level, Not Per-Model

OpenRouter free-tier limits are generally enforced **per account**, not as a separate budget per model. If you exhaust your free quota on one model, other free models in the same account may also become unavailable until the period resets. This is why heavy use of `openrouter/free` or any single endpoint can lock you out of the entire free tier.

---

## What `openrouter/free` Does

`openrouter/free` is a **router**, not a model. When you request it, OpenRouter picks from currently available free backends. The specific backend is **not stable**: the same prompt may hit different models on different days or under different load. Use it when:

- You want to test prompts without picking a specific model.
- All named free endpoints are throttled.
- You are prototyping.

Do **not** use it when reproducibility matters.

---

## Fair Benchmarking Procedure

To compare free models honestly:

1. **Same prompt set.** Use 10–30 prompts covering: short Q&A, summarization, code generation, code explanation, classification, creative rewrite, multi-step reasoning, refusal/edge cases, and JSON/tool-call output.
2. **Identical parameters.**
   - `temperature: 0` for grading stability.
   - `max_tokens: 512` (or task-appropriate).
   - `top_p: 1.0`.
   - `frequency_penalty: 0`, `presence_penalty: 0`.
3. **Identical system prompt.** A neutral "You are a helpful assistant." unless the model is specialized.
4. **Run multiple seeds** if you keep temperature > 0.
5. **Evaluate with a rubric:**
   - Factual correctness (1–5)
   - Instruction following (1–5)
   - Conciseness (1–5)
   - Hallucination count
   - Format adherence (JSON validity, etc.)
6. **Measure latency** end-to-end, including queue time, on the same network.
7. **Document failures** (refusals, timeouts, errors) — these matter as much as wins.
8. **Repeat on different days** to capture free-tier variability.

---

## Example API Calls

> Replace `YOUR_KEY` with your OpenRouter key. These examples use the recommended defaults.

### Best Default — `minimax/minimax-m3:free`
```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "minimax/minimax-m3:free",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain why a large context window does not imply higher intelligence."}
    ],
    "temperature": 0,
    "max_tokens": 512
  }'
```

### Best Coding — `poolside/laguna-s-2.1:free`
```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "poolside/laguna-s-2.1:free",
    "messages": [
      {"role": "system", "content": "You are an expert programmer."},
      {"role": "user", "content": "Write a Python function that flattens a nested list of arbitrary depth."}
    ],
    "temperature": 0,
    "max_tokens": 512
  }'
```

### Fastest Lightweight — `liquid/lfm-2.5-2.6b:free`
```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "liquid/lfm-2.5-2.6b:free",
    "messages": [
      {"role": "system", "content": "Classify the intent of the user message."},
      {"role": "user", "content": "Reset my password please."}
    ],
    "temperature": 0,
    "max_tokens": 64
  }'
```

### Long-Context — `nvidia/nemotron-3-ultra-550b-a55b:free`
```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "messages": [
      {"role": "system", "content": "Summarize the document and list key risks."},
      {"role": "user", "content": "<paste long document here>"}
    ],
    "temperature": 0,
    "max_tokens": 800
  }'
```

### Reasoning — `minimax/minimax-m3:free`
```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "minimax/minimax-m3:free",
    "messages": [
      {"role": "system", "content": "Think step by step before answering."},
      {"role": "user", "content": "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost?"}
    ],
    "temperature": 0,
    "max_tokens": 512
  }'
```

### Safety Classification — `nvidia/nemotron-3.5-content-safety:free`
```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nvidia/nemotron-3.5-content-safety:free",
    "messages": [
      {"role": "system", "content": "Classify the user message as SAFE or UNSAFE. Respond with only the label."},
      {"role": "user", "content": "How do I bake a chocolate cake?"}
    ],
    "temperature": 0,
    "max_tokens": 16
  }'
```

### Audio Generation — `google/lyria-3-pro-preview`
```bash
curl https://openrouter.ai/api/v1/audio/generations \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/lyria-3-pro-preview",
    "prompt": "A calm piano melody with soft strings.",
    "duration_seconds": 20
  }'
```

---

## Decision Guide

| If you need… | Use… |
|---|---|
| A reliable general-purpose default | `minimax/minimax-m3:free` |
| Strong, code-specialized output | `poolside/laguna-s-2.1:free` |
| The lowest latency possible | `liquid/lfm-2.5-2.6b:free` or `thinkingmachines/inkling-small:free` |
| Long-document summarization | `minimax/minimax-m3:free` or `nvidia/nemotron-3-ultra-550b-a55b:free` |
| Hard multi-step reasoning | `minimax/minimax-m3:free` |
| Content moderation / safety classification | `nvidia/nemotron-3.5-content-safety:free` |
| Stable fallback when M3 is throttled | `minimax/minimax-m2.7:free` |
| Multilingual (Chinese/English) | `z-ai/glm-5.2:free` |
| Routing/intent classification | `liquid/lfm-2.5-2.6b:free` or `thinkingmachines/inkling-small:free` |
| Audio/music generation | `google/lyria-3-pro-preview` |
| Short audio clips | `google/lyria-3-clip-preview` |
| Experimentation when nothing else is available | `openrouter/free` |
| Medical/clinical text | `inclusionai/ling-3.0-flash-sante:free` |
| Financial text | `inclusionai/ling-3.0-flash-fin:free` |

---

## Closing Notes

- **Free models are exploration tools.** For production reliability, use paid endpoints.
- **Always confirm current pricing, quotas, and availability** on each model's OpenRouter page before integrating.
- **Treat preview models** (`dots-3-note-preview`, `lyria-3-pro-preview`, `lyria-3-clip-preview`) as unstable.
- **Build fallback chains.** If your primary free model is unavailable, have a secondary free model and a paid fallback.
- **Benchmark for your workload.** Use the procedure above; rankings here are qualitative.
```
