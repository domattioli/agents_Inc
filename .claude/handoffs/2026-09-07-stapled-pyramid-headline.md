# Session Handoff: Reliability-weighted pyramid scoring for stapled-news headlines

**Date:** 2026-09-07
**Project:** cross-repo — `stapled-news` (https://github.com/domattioli/stapled-news) + pyramid-scoring engine (`DomI-jsonl/skills/nested-notes/benchmarks/pyramid_report.py`) + dispatch fanout via `agents_Inc`
**Session Duration:** ~2.5 hours

## Current State

**Task:** Investigate combining stapled-news's Dawid-Skene EM (per-outlet reliability inference) with the Pyramid summarization-scoring method (SCU extraction + corroboration-weighted claim scoring) to get past "consensus, not truth" and synthesize a substantiated headline.
**Phase:** spike / proof-of-concept, adversarially reviewed — NOT yet a validated method, NOT yet implemented as a real feature.
**Progress:** PoC ran and produced a real divergence between naive-count and reliability-weighted scoring, but an independent model review (Luna) found 5 critical/high logical issues with the PoC's validity. Spec/plan for a production version exists but has NOT been implemented (`speckit-implement` was deliberately not run).

## What We Did

1. Recon'd both source systems: `stapled-news`'s `src/stapled/infer/em.py` (`_run_em_single`, real Dawid-Skene binary EM) and the pyramid-scoring engine's SCU (Summary Content Unit) extraction/weighting method (Nenkova & Passonneau 2004).
2. Found a real multi-outlet event already in stapled-news's local corpus (no new downloads): 15 major outlets covering Maine's 2026 Senate Democratic nomination of Troy Jackson replacing Graham Platner (`corpus/us/headlines.csv.gz` in a scratch clone at `/tmp/stapled-news-peek` — **this clone is ephemeral, re-clone in the new environment**).
3. Hand-extracted 6 SCUs from the 15 headlines, fed them into stapled-news's real (unmodified, imported) `_run_em_single` as one binary "micro-event" per SCU, got per-outlet reliability estimates.
4. Built a reliability-weighted pyramid (SCU weight = Σ reliability of asserting outlets) vs. the pyramid method's native naive-count weighting, scored 3 candidate headlines against both.
5. Result: the two weightings gave different scores for the same winning headline (0.65 naive vs 0.70 reliability-weighted) — treated in the moment as evidence the fix works. **This claim did not survive review — see Blockers.**
6. Dispatched a haiku-supervised `speckit-pipeline` run (specify→clarify→plan→tasks→checklist→analyze, no implement) inside the scratch clone, producing a full spec for a production "reliability-weighted pyramid scoring for headline synthesis" feature.
7. Wrote a published-scientist-register methodology skeleton with stubbed SUCCESS/FAILURE branches (scratchpad, ephemeral — full text reproduced below since it won't survive to a new environment).
8. Dispatched Luna (GPT-5.6, via `agents_Inc`'s `codex-bridge`) to adversarially review the PoC script. It returned 5 critical/high findings (below) — this is the most important thing to read first in the new environment.
9. Filed and fixed one infra bug, filed one feature request, both in `agents_Inc`:
   - **Fixed:** `skills/codex-bridge/scripts/up.sh` hardcoded a stale pre-rename path (`/Users/domattioli/Projects/workerbees`) as `BASE`; `--workdir` never actually overrode it. Fixed to resolve `BASE` from the script's own location. Issue: https://github.com/domattioli/agents_Inc/issues/6 (fix applied same session, not yet committed — working tree has the diff).
   - **Filed, not built:** CLI-agnostic / inverse dispatch mechanism so a Codex-driven session can call Claude models the same way `codex-bridge` lets Claude call Codex. Issue: https://github.com/domattioli/agents_Inc/issues/7.

## Decisions Made

- **Classified as a Spike, not architectural work** (per `superpowers:brainstorming`) — throwaway PoC code, answer is a recommendation, not a shipped feature. Still true after Luna's review; if anything Luna's findings reinforce that this needs more validation before it graduates past spike.
- **Reused stapled-news's actual `_run_em_single` unmodified** rather than reimplementing Dawid-Skene, to keep the PoC honest about what it's testing (the reliability-weighting idea, not a new EM implementation).
- **Fanout used agents_Inc vocabulary**: scouts (free/luna, no tools) for recon, haiku/luna for workhorse (SCU extraction, speckit execution, review), exec (Sonnet, this session) for judgment calls and synthesis — per explicit operator instruction at session start.
- **Did not run `speckit-implement`** — spec/plan/tasks only, per this project's general policy that code-writing is a separate, later, explicitly-approved dispatch.
- **Did not apply the dangerous sandbox override** (`CODEX_BRIDGE_ALLOW_DANGER=1`) to work around the bridge bug — fixed the actual path bug instead, kept `workspace-write` sandbox.

## Luna's Review Findings (READ THIS FIRST in the new environment — the PoC's headline claim is not validated)

Adversarial review of `/tmp/poc_em.py` (script reproduced in full below) via `codex-bridge ask --model gpt-5.6-luna`. Verbatim findings, paraphrased for length:

1. **Dawid-Skene label-switching / no anchor**: no gold labels or trusted-outlet prior means EM can flip which latent state is "true" — `sens`/`spec`/reliability aren't guaranteed truth-oriented, just self-consistent with an arbitrary label.
2. **Absence-as-denial bug**: `obs = 1 if fn(headlines[o]) else 0` codes "headline doesn't mention this claim" as "headline asserts this claim is false." A binary Dawid-Skene model interprets `0` as an active false claim, not silence. This can invert reliability estimates.
3. **Circularity**: outlet reliability is estimated from the same SCU-assertion pattern it's then used to reweight — this reweights the observed consensus using a latent variable fitted to that same consensus, not an independent correction.
4. **No ground truth = no truth claim supported**: two schemes producing different scores (0.65 vs 0.70) proves the scores differ, not that the reliability-weighted one is more accurate. **This directly undercuts the session's headline claim that the PoC "fixes consensus, not truth."** It shows the method is *different*, not that it's *better*.
5. **SCU independence violated**: nomination / Platner-replacement / convention-process are causally entangled facts about one event, not independent binary items — likely violates whatever independence assumption `_run_em_single` makes about "events."

Luna could not audit `_run_em_single`'s internals or the candidate-scoring code directly (wasn't given those files) — only reviewed the PoC script's construction and the description of the method.

## Code — PoC script (full, for reproducibility; scratch clone `/tmp/stapled-news-peek` is ephemeral)

```python
import sys
sys.path.insert(0, '/tmp/stapled-news-peek/src')
from stapled.infer.em import _run_em_single
from stapled.infer.model import RunConfig
import numpy as np, json

headlines = {
"abcnews.go.com": "How Troy Jackson went from Maine logger to the Democratic nominee for Senate against Susan Collins",
"axios.com": "Troy Jackson poised to seize Maine baton after Platner's exit",
"breitbart.com": "GOP Rep Says Troy Jackson May Not Qualify for Maine Senate Nomination",
"cbsnews.com": "Maine Democratic Senate race narrows as candidates rally behind Troy Jackson",
"cnn.com": "Maine Democrats pick Troy Jackson as their Senate nominee at an unusual party convention",
"foxnews.com": "Maine Democrats crown Troy Jackson as Platner replacement as fresh scrutiny clouds Senate reset",
"huffpost.com": "Troy Jackson Secures Democratic Nomination For U.S. Senate In Maine",
"nbcnews.com": "Democrats nominate Troy Jackson to replace Graham Platner in must-win Maine Senate race",
"npr.org": "Democrats in Maine formally nominate Troy Jackson as their new U.S. Senate candidate",
"nytimes.com": "5 Things to Know About the Maine Senate Candidate Troy Jackson",
"politico.com": "How Republicans plan to conquer Troy Jackson",
"theguardian.com": "Graham Platner is out. Troy Jackson should replace him | Dustin Guastella",
"thehill.com": "Democrats have a real shot in Maine, but Troy Jackson could ruin it",
"washingtonpost.com": "Maine Democrats rally around logger Troy Jackson to replace Graham Platner",
"wsj.com": "Maine Democrats Choose Troy Jackson to Replace Graham Platner in Key Senate Race",
}

# SCUs (atomic claims), hand-labeled by keyword presence in headline text (PoC-grade extraction).
# KNOWN BUG per Luna review #2: absence of a keyword is coded observation=0 ("false"),
# not "not mentioned" — fix before reusing this pattern.
scus = {
    "S1_is_nominee": lambda h: any(k in h.lower() for k in ["nominee", "nominate", "pick", "choose", "chosen", "secures democratic nomination", "crown"]),
    "S2_replaces_platner": lambda h: "platner" in h.lower(),
    "S3_is_logger": lambda h: "logger" in h.lower(),
    "S4_opponent_collins": lambda h: "collins" in h.lower(),
    "S5_convention_process": lambda h: "convention" in h.lower(),
    "S6_race_high_stakes": lambda h: any(k in h.lower() for k in ["must-win", "key senate race", "ruin it", "real shot"]),
}

outlets = sorted(headlines.keys())
claims_by_event = {}
for scu_id, fn in scus.items():
    claims_by_event[scu_id] = []
    for o in outlets:
        obs = 1 if fn(headlines[o]) else 0
        claims_by_event[scu_id].append({"outlet_id": o, "observation": obs, "certainty": 0.9, "magnitude": None})

outlet_idx = {o: i for i, o in enumerate(outlets)}
config = RunConfig(max_iter=200, tol=1e-6, restarts=5, concentration_threshold=0.6)

best = None
best_ll = -np.inf
for r in range(config.restarts):
    run = _run_em_single(claims_by_event, outlets, outlet_idx, config, seed=42+r)
    if run and run["log_likelihood"] > best_ll:
        best_ll = run["log_likelihood"]
        best = run

# ... (rest: prints reliability table + SCU posteriors, dumps /tmp/poc_em_result.json)
```

Candidate-scoring step (reliability-weighted vs naive-count pyramid recall) is a separate ~40-line script, not reproduced here in full — re-derive from the SCU weight table logic: `weight[scu] = sum(outlet_reliability[o] for o in outlets if scu_fn(headlines[o]))` vs `raw_count[scu] = count(...)`, then `weighted_recall = sum(weight[s] for s in candidate_scus) / sum(weight.values())`.

## Methodology doc (published-scientist register, full text — scratchpad copy is ephemeral)

Written via `write-like-scientist` skill, stubbed SUCCESS/FAILURE branches. **Given Luna's review, the FAILURE branch is now the operative one** — update on resume:

> # Reliability-weighted pyramid scoring recovers claims that naive outlet-count consensus discards
>
> ## Motivation
> `stapled-news` infers per-event true state and per-outlet reliability by Dawid-Skene EM over binary claims, reliability-weighted rather than raw-count-weighted, but produces a binary state per event: no synthesized text, no per-claim evidence, no ranking of candidate headlines. The Pyramid method (Nenkova & Passonneau, 2004) extracts atomic claims (SCUs), weights each by source count, scores candidates by recovered weight, with evidence citations. Both weight by corroboration; neither alone distinguishes corroboration from correctness — naive Pyramid weighting counts sources, not reliability.
>
> ## Method
> 1. Event selection from existing local corpus, no new data collection.
> 2. SCU extraction per outlet headline (keyword-based at PoC grade).
> 3. Each SCU treated as one binary micro-event across outlets, fed to `stapled-news`'s unmodified `_run_em_single`.
> 4. SCU weight redefined as Σ(reliability of asserting outlets), replacing raw count.
> 5. Candidates scored for weighted recall against both pyramids, rankings compared.
>
> ## Results — [now FAILURE branch, per Luna's review]
> Observed failure mode: reliability weighting diverges from naive consensus (0.65 → 0.70 for the same winning headline), but the divergence carries no independently-verified correctness signal — a changed score is not evidence of improved validity (Luna finding #4). Contributing causes: circularity between reliability estimation and the consensus it reweights (finding #3), absence-as-denial coding bug inflating apparent disagreement (finding #2), no anchor/gold-label breaking Dawid-Skene identifiability (finding #1), and an independence violation from treating causally-entangled SCUs as separate EM events (finding #5). This is likely a property of single-event, no-anchor reliability estimation specifically, not a disproof of the reliability-weighted-pyramid idea in general — re-test needs either (a) a cross-event corpus large enough to fit `_run_em_single` as originally designed (many events, not many SCUs-within-one-event) and/or (b) an anchor: at least one outlet or claim with independently verified ground truth to break label-switching.
>
> ## Limitations
> - SCU extraction is keyword-based, not validated.
> - Absence ≠ denial conflation (see Luna #2) — not yet fixed.
> - Single-event reliability estimation conflates within-event agreement with cross-event reliability, which is what `stapled-news`'s EM is actually designed to use.
>
> ## Provenance
> `stapled-news`: https://github.com/domattioli/stapled-news. Pyramid method: Nenkova & Passonneau (2004), HLT-NAACL.

## Open Questions

- [ ] Is the "reliability-weighted pyramid" idea worth re-testing properly (cross-event corpus + an anchor), or does Luna's circularity finding (#3) kill it structurally regardless of scale?
- [ ] If re-tested: fix the absence-as-denial bug first (code non-mention as missing/abstain, not `observation=0`) — likely changes results substantially.
- [ ] Spec at `specs/004-reliability-pyramid-scoring/` (in the ephemeral `/tmp/stapled-news-peek` clone) assumed the PoC's premise was sound — it was written *before* Luna's review landed. Needs a pass to add: (a) exception-handling section (flagged separately by the speckit `analyze` step — invalid event-id, missing file, EM non-convergence), (b) a re-scoped success criterion that accounts for Luna's findings (i.e., don't spec "detect the truer headline," spec "detect where naive and reliability-weighted scoring diverge and surface both, pending a validated correctness signal").
- [ ] Headline candidates in the current spec are user-provided, not auto-generated — confirm that's the intended scope before implementing.

## Blockers / Issues

- **The scratch clone `/tmp/stapled-news-peek` and everything under `/tmp/` (PoC scripts, EM result JSON) and the session scratchpad (methodology doc) do not persist to a new environment.** Re-clone `https://github.com/domattioli/stapled-news` fresh; the PoC script above is fully reproducible from this document alone.
- `agents_Inc/skills/codex-bridge/scripts/up.sh` fix (stale `BASE` path) is applied in the local working tree but **not committed**. Check `git status` in `agents_Inc` on resume — may need to commit/push or it'll look uncommitted/lost.
- No stapled-news reliability scores exist for arbitrary outlet sets from the shipped `consensus.json` (that's from a different 811-outlet corpus snapshot) — any real run needs to compute reliability fresh per event-set, as the PoC did.

## Context to Remember

- Operator's fanout convention (this session): scouts = free/luna models, no tools, recon only; workhorses = haiku/luna, mechanical/bounded execution; exec = the Sonnet session, judgment calls and synthesis. Established via explicit instruction, not a written policy doc — carry forward if resuming with the same dispatch pattern.
- `agents_Inc` (this repo) has its own binding `CLAUDE.md` governance (rung ladder, 14-element delegation contract, caveman/nested-notes doc-audience rules) — read it fresh in the new environment, don't assume this doc's informal tone reflects that repo's actual dispatch requirements for any new delegated work.
- User explicitly asked to exclude security discussion from this handoff (there was a prior HTTP/tunnel security exchange about `codex-bridge` this session — deliberately omitted here per instruction, not forgotten).

## Next Steps

1. [ ] Decide: abandon the reliability-weighted-pyramid idea, or re-test with an anchor + cross-event corpus + absence-as-denial fix.
2. [ ] If continuing: commit the `codex-bridge/scripts/up.sh` fix in `agents_Inc` (currently uncommitted).
3. [ ] If continuing: revise `specs/004-reliability-pyramid-scoring/spec.md` (re-clone `stapled-news` first) to reflect Luna's findings before any implementation.
4. [ ] Either way: update the methodology doc's operative branch (FAILURE, per above) and decide whether it's worth publishing anywhere or was purely investigative.

## Files to Review on Resume

- This document — self-contained, no other file dependency required to understand what happened.
- `https://github.com/domattioli/agents_Inc/issues/6` — bridge path bug (fixed, uncommitted locally).
- `https://github.com/domattioli/agents_Inc/issues/7` — CLI-agnostic dispatch mechanism (filed, not built).
- `https://github.com/domattioli/stapled-news` `src/stapled/infer/em.py` — the real EM code the PoC reused; re-clone fresh.
