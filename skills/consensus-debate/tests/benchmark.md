# Benchmark — `consensus-debate`

## Metric

`rounds_to_consensus_and_fake_consensus_rate` — two numbers per run:

1. Rounds until both debaters sign the same consensus block (or the moderator calls deadlock). Lower is better, provided the result is real.
2. Fake-consensus count: final-block items that a later check showed the debaters did not actually agree on, or that cite a file, function, or flag that does not exist. Target: 0.

## Measurement protocol

- Save transcripts per the skill's Transcripts section.
- Count rounds from the saved `*_r<N>_out.md` files.
- Before reporting, grep every path, function, and flag named in `CONSENSUS.md`. Count each miss as one fake-consensus item.
- Record token use from the Codex `turn.completed` usage event and the Claude `subagent_tokens` figure. Both are cumulative, so report per-round deltas.

## Results

| version | date | run | rounds | fake consensus | notes |
|---|---|---|---|---|---|
| 0.2.0 | 2026-09-22 | ollama in agents_Inc, fable vs astra @ medium | 4 (3 full + 1 single-item) | 0 (all final-block paths grep-verified: `pipeline.py:208`, `router.py:68,70-71`, `policy.py:14-19,23-27`, `doctor.py:104`, `base.py:17`) | baseline run; v0.1 → v0.2 added crossed-round repair, fixed-form final round, cumulative-token note |
