# Proposal (issue-ready): route dispatches by data classification, not by cipher

Status: **proposed, not a spec.** Drafted 2026-09-12 as a scoping pass. Ready to paste as a GitHub issue body (this repo tracks proposed-not-yet-committed work as issues — see #3 "Brainstorm:", #7 "feat:"; `specs/NNN-*` is for work already committed to, `docs/adr/*` for accepted rulings). No GitHub issue was created by the drafting session.

Confidentiality: internal working doc. If filed as an issue it inherits this repo's normal issue visibility.

## 0. Why this exists

A prior recon asked whether deterministic encode/decode ciphering of prompts could protect unpublished IP from free-tier provider training. Conclusion: not plausible as a whole-prompt cipher — task usefulness requires semantic legibility, which is the same variable that drives extraction risk; determinism makes a fixed cipher learnable at scale; per-call random keys destroy usefulness instead. Recon's alternative: **route by data classification**. IP-bearing work goes to zero-egress or contractual no-train paths; free third-party tiers get only generic / redacted / abstracted work.

This proposal scopes what operationalizing that would actually mean here. It does not implement anything.

## 1. What "IP-bearing" vs "generic" would mean for a dispatch

The mechanism already exists on the programmatic path and is **absent on the human/agent prompt path**. Two distinct dispatch surfaces:

### 1a. Programmatic path (`workerbees/`) — mechanism exists, semantics thin

- `workerbees/envelope.py:63` — `VALID_CLASSIFICATIONS = {"public", "internal", "confidential", "restricted"}`; `Envelope.data_classification` is a required field, validated in `validate()`.
- `workerbees/registry.py:7` — `CLEARANCE_LEVELS = {"public":0,"internal":1,"confidential":2,"restricted":3}`; every agent in `workerbees/governance.json` carries a `clearance`.
- `workerbees/policy.py:93-106` — `evaluate()` fails closed on unknown clearance (D3) and denies `CLASSIFICATION_EXCEEDED` unless **both** sender and recipient clearance ≥ envelope classification (D2).
- `workerbees/policy.py:23-27` — `check_dispatch()` raises `WB_WORKSPACE_AUTH_REQUIRED` when an *optional* provider (gemini/mistral/openrouter, per `workerbees/routing.json`) would receive `confidential=True` without a per-workspace grant file `<workspace>/.workerbees/authorization.json` (`is_authorized`, `policy.py:14-21`). This is ADR-0002 / D7.

Gap: the classification carried into the envelope is a **boolean, not a taxonomy**. `workerbees/pipeline.py:183` and `workerbees/reviewer.py:73` both compute `data_classification="confidential" if confidential else "public"` — so `internal` and `restricted` are unreachable in practice, and there is no notion of *why* something is confidential (client document vs unpublished repo IP). `brief()` defaults `confidential=True` (`pipeline.py:191`), per D-log entry on worker clearance; the flag is a caller argument with no classifier and no per-source inference.

Second gap: recipient clearance is checked against a **registry agent**, not against the **provider/egress destination**. Provider-egress control lives only in `check_dispatch`, and only as the optional-provider deny. So "this model runs on someone else's servers under a train-on-input tier" is not a modeled property of a route.

### 1b. Human/agent dispatch path (`skills/workerbee`, `skills/codex-bridge`) — tag exists, enforcement does not

- `skills/workerbee/SKILL.md:435` mandatory element 8 = "Confidentiality/data-classification tag. State classification of content the delegate handles (e.g. public / confidential)."
- `skills/workerbee/scripts/check_dispatch_prompt.py:27` lints for element 8 by keyword match: `8: ["classification", "confidential", "internal"]`.
- That is a **prose lint on the prompt text**. Nothing reads the tag and nothing constrains which model the tag permits. A prompt can say "confidential" and still be sent to a free tier.
- `skills/codex-bridge/scripts/route.sh` picks a backend chain purely from `task_class` × `CODEX_BRIDGE_MODE` (standard/budget/ultra). No classification input.
- The only egress-side mitigation today is `skills/codex-bridge/scripts/data_policy.py` — an in-band "DO NOT TRAIN" opt-out payload appended to prompts, env-gated by `CODEX_BRIDGE_OPTOUT`, wired only into `gask.sh:176`. It is a request to the provider, not a control; it is not a substitute for routing.

### Proposed semantics (for the operator to ratify, not settled here)

- Reuse the existing 4-level taxonomy rather than inventing a parallel one. Candidate mapping: `public` = synthetic/fixture/published; `internal` = repo-generic (no unpublished design); `confidential` = client documents (ADR-0002's original case); `restricted` = **unpublished IP** — the new case this proposal is about.
- Add an egress property to routes/models (not to agents): something like `egress: local | subscription | free-tier` plus a `train_on_input: yes|no|contractual-no` on each entry in `workerbees/models.json`. Then classification→egress becomes a table, and `restricted` can be made unroutable to anything with `train_on_input: yes` with no per-workspace override.

## 2. Where enforcement would live (actual paths)

| Layer | File | Change shape |
|---|---|---|
| Taxonomy plumbing | `workerbees/pipeline.py:183`, `workerbees/reviewer.py:73` | replace boolean→two-value mapping with a passed-through classification string; keep `confidential=True` default behavior as `confidential` for compatibility |
| Caller surface | `workerbees/pipeline.py:191` (`brief(...)`), `workerbees/bench.py:23`, `scripts/proof/audit_parity.sh:30` | accept/forward a classification argument |
| Route/egress metadata | `workerbees/models.json` (every entry), `workerbees/routing.json` | add egress / train-on-input fields; note `tests/test_vocab_drift_guard.py` already asserts `models.json` tier values against the live rung table — a new field needs its own guard or that test extended |
| Route filtering | `workerbees/router.py` (`_eligible`, `_provider_routes`, `pick_model_chain`) | classification becomes a filter dimension alongside `task`/`tier`; currently `pick_model_chain` takes `workspace_authorized` only |
| Policy deny | `workerbees/policy.py:23-27` (`check_dispatch`) | generalize from "optional provider + confidential" to a classification×egress matrix; add a reason code for the restricted case |
| Registry/governance | `workerbees/governance.json`, `workerbees/registry.py` | version + `policy_version` bump (currently `2026-09-05.4`); possibly a clearance change per-agent |
| Human-path lint | `skills/workerbee/scripts/check_dispatch_prompt.py:27` | element-8 check could require one of the four taxonomy words, not any keyword; still advisory-only |
| Human-path routing | `skills/codex-bridge/scripts/route.sh` | would need a classification input to gate the free-tier chains (`budget`/`ultra` modes route to gemini/mistral/openrouter) |
| Doc/canon | `CONTEXT.md` (has "Workspace authorization" entry), `docs/DECISIONS.md`, new `docs/adr/0004-*.md` | ADR-0002 is the thing being extended; it explicitly names "deterministic synthetic redaction" as unscheduled future work |

Tests that would move: `tests/test_policy.py`, `tests/test_governance_matrix.py`, `tests/test_dispatch_contract.py`, `tests/test_envelope.py`, `tests/test_governance_negatives.py` all already assert on classification behavior.

## 3. What "local model" / "no-train tier" options actually exist here

Read before claiming — the honest inventory:

- **No local-model runner is wired in anywhere.** Zero hits for `ollama`, `llama.cpp`, `lmstudio`, "local model", "on-device" across `*.md`/`*.py`/`*.sh`/`*.json` in the repo. `workerbees/adapters/` contains exactly `base.py`, `claude.py`, `codex.py`. `workerbees/models.json` has no entry with a local provider (providers present: claude 4, codex 5, openrouter 23, gemini 2, mistral 1 — all remote).
  - Note 2026-10-03: this inventory predates the Ollama adapter (agents_inc/adapters/ollama.py).
- **The HTTP adapter seam is unbuilt.** `workerbees/pipeline.py:165` — `_cmd()` raises `NotImplementedError(f"{route.provider}: http adapters land post-Phase-1")`. Optional providers are reachable only through the shell wrappers named in `routing.json` (`skills/codex-bridge/scripts/{gask,mask,oask}.sh`), not through the governed pipeline. So a local adapter would be new work, but it would land in a seam that already exists structurally (`adapters/` + `Route.cmd_kind`).
- **"No-train tier" today = the required providers.** `routing.json` `"required": ["claude","codex"]` are subscription CLI paths; ADR-0002 already treats them as the default path for confidential work ("Default Tim path uses only Claude+Codex"). Whether the *subscription* terms actually constitute a contractual no-train guarantee is **not documented anywhere in this repo** — that is an operator/legal question, not a code question (see open questions).
- **`data_policy.py`'s opt-out payload is not a control.** It is an in-band declaration appended to the prompt, enabled by default (`CODEX_BRIDGE_OPTOUT` unset ⇒ enabled) and wired only in `gask.sh`. Treating it as protection for unpublished IP would be the same category error as the cipher idea.
- Missing if this ships: a local runner + adapter; an egress/train-on-input field in the model catalog; any written record of provider terms per route.

## 4. Phased shape (for a Supervisor to turn into tasks — tasks NOT written here)

- **Phase 0 — decide.** Operator ratifies the 4-level mapping (esp. what `restricted` means), and whether subscription providers count as no-train. Output: a `docs/DECISIONS.md` entry + ADR extending ADR-0002. No code.
- **Phase 1 — classify-only (observe, deny nothing new).** Plumb a real classification string end-to-end (`brief()` → envelope → ledger), add egress/train-on-input metadata to `workerbees/models.json`, and record the classification×route pair on every dispatch in the ledger. Shadow semantics only: existing denies unchanged. Deliverable = you can answer "what classification of content went to which egress class, historically."
- **Phase 2 — enforce on the governed path.** Generalize `check_dispatch` + `router.pick_model_chain` to a classification×egress matrix; make `restricted` unroutable to train-on-input providers with no workspace-authorization escape hatch (deliberately unlike D7's `confidential` case). Governance version bump; negative tests.
- **Phase 3 — human/agent path.** Tighten element-8 lint to the taxonomy vocabulary; give `route.sh` a classification input so `budget`/`ultra` free-tier chains refuse restricted content. Accept that this layer is advisory (a prompt author can lie) and say so in the SKILL body.
- **Phase 4 (optional, gated on Phase 0) — zero-egress path.** Local adapter (`workerbees/adapters/local.py`) + catalog entries + doctor availability probe, so `restricted` has somewhere to go rather than only somewhere to be refused. Only worth doing if Phase 0 says subscription ≠ acceptable for restricted.

Each phase is independently shippable and each earlier phase is useful alone. Phase 1 without Phase 2 is the conservative start: it produces evidence about whether any IP-bearing dispatch has actually been leaving via free tiers.

## 5. Open questions for the operator

1. **Is `restricted` the right slot for unpublished IP, or does IP-bearing need its own axis?** Classification today is a single ordered scale; "client-confidential" and "our own unpublished IP" may not be comparable on one line.
2. **Do the Claude/Codex subscription terms constitute a no-train guarantee?** Nothing in-repo documents this. If not, Phase 4 (local) stops being optional.
3. **Should `restricted` be overridable by `.workerbees/authorization.json`?** D7 lets a workspace grant free-tier access to `confidential`. This proposal assumes `restricted` is *not* overridable. Needs a ruling.
4. **Who classifies?** Caller-declared (today's shape, cheap, lie-able), a Grunt-rung classifier dispatch (adds cost + a bootstrap problem: the classifier sees the content), or path-based rules (e.g. anything under `specs/` unpublished ⇒ restricted). Scout-class question.
5. **Does the in-band `data_policy.py` opt-out stay?** It is harmless but may create false confidence. Keep as-is, demote to documented-as-non-control, or drop?
6. **Default classification if unstated.** `brief()` currently defaults `confidential=True`. Does an unstated classification become `restricted` (fail-closed, may block routine work) or stay `confidential`?
7. **Scope of enforcement:** governed `workerbees/` path only, or also the human dispatch path that most real work actually uses today? The second is where the leak risk lives and is the layer that can least be enforced.
