# Operating the governance control plane

Human doc. What the governance slice does, what it does not do, how to turn it on, and how to turn it off again.

## What it is

- **A boundary between a prompt and a dispatch.** In shadow and enforce, every model call the pipeline makes — worker, correction, reviewer, doctor probe — passes through one gateway that decides, records the decision, and only then invokes the provider.
  - **Deterministic.** The decision comes from a versioned JSON graph and a pure evaluation function. No model is consulted, and nothing in the source text can reach the decision.
- **Auditable admission.** Gateway decisions write to `control.sqlite`. Normal admission rows carry authenticated sender, recipient, operation, verdict, reason code, checked rules and policy version. Validation failures can lack identity or operation because the envelope was not trusted. A control-store failure blocks dispatch. This is decision evidence, not a complete reconstruction of provider execution or cost.
  - **Additive.** Governance changes the audit trail, not the answer. The same brief returns the same status with the flag off, in shadow, or in enforce.

## The flag

- **`WORKERBEES_GOVERNANCE`** takes exactly three values. Any other value fails at startup rather than degrading to a default.
  - **`off`** — the default. Prior behavior, byte for byte. No registry is loaded and no gateway is built.
  - **`shadow`** — decisions are evaluated and recorded; execution proceeds regardless of the verdict. Use it to see what enforce would do before enforce can block anything.
  - **`enforce`** — a denial stops the call. The runner is invoked zero times and the denial is on record.

## What enforce actually blocks

- **Unregistered parties and unauthorized edges.** A sender or recipient absent from `governance.json`, or a pair with no `delegates_to` relationship, is denied `NO_EDGE` or `UNKNOWN_SENDER`/`UNKNOWN_RECIPIENT`.
- **Classification above clearance.** Confidential input to an agent cleared only for internal or public data is denied `CLASSIFICATION_EXCEEDED`.
- **Spoofed identity.** The sender is taken from the trusted local context, never from the message. A mismatch is denied `SENDER_MISMATCH` and, since T15, recorded like every other denial.
- **Replay and tampering.** A repeated message id with the same content returns status `duplicate` (reason code `DUPLICATE`) without a second call; the same id with changed content returns status `conflict`, recorded as `REPLAY_CONFLICT`.
- **Unapproved actions.** An envelope that requires approval and does not carry it is denied `APPROVAL_REQUIRED`.
- **Same-vendor review.** A reviewer route matching the worker's provider is refused in every mode, including when the caller supplies the route explicitly.
- **The codes above are the policy denials you will meet in normal use.** The gateway also emits infrastructure and audit codes — `NO_REGISTRY`, `AUDIT_UNAVAILABLE`, `ENVELOPE_INVALID`, `PROVIDER_NOT_EXECUTABLE`, `EXPIRED`, `CANCELLED`, `BUDGET_EXCEEDED`, `POLICY_ERROR` among them. Read the reason code on the row rather than guessing from the status.

## What it does not do

- **It does not enforce token budgets.** No CLI adapter exposes a hard total-token bound, so token budgets are recorded as unknown rather than enforced. Treat a character estimate as an estimate.
- **It does not serialize a run.** Reservations are keyed per node, so two nodes in one run hold reservations at once and their call counts sum. The "one model call at a time" rule in the assessment is not implemented.
- **It does not govern the legacy runner.** Work dispatched outside this pipeline is ungoverned, and a process with the owner's privileges can bypass library code entirely. The claim covers tool-free worker processes, not a hostile host.
- **It does not make output true.** A permitted call is still subject to the verifier and the reviewer. Authorization is not acceptance.

## Turning it on

1. Confirm the suite is green: `python3 -m unittest discover -s tests`.
2. Run the demo to see one allowed and one denied trace end to end: `PYTHONPATH=. python3 tools/governance_demo.py --fake`.
3. Set `WORKERBEES_GOVERNANCE=shadow` and run real work. Read `.workerbees/control.sqlite` and confirm every model call has a decision row and that no decision you depend on comes back denied.
4. Only then set `WORKERBEES_GOVERNANCE=enforce`.

## Turning it off

- **Unset the variable, or set it to `off`.** Nothing else is required: no migration, no cleanup, no schema change. The decisions already written stay readable, and the pipeline returns to its prior code path immediately.
- **A denial that surprises you is a configuration question, not a code question.** Read the reason code on the decision row, then fix `governance.json` and bump its `version` and `policy_version` together.

## Where things live

- **`workerbees/governance.json`** — agents, capabilities, relationships, clearances, versioned.
- **`workerbees/protocols.json`** — bounded operation schemas.
- **`workerbees/routing.json`** — the model table, and nothing else. Governance never edits it.
- **`<workspace>/.workerbees/control.sqlite`** — decisions, reservations, replay keys, approvals.
- **`<workspace>/.workerbees/ledger.jsonl`** — the invocation graph. Best effort: a failed ledger write is recorded and the outcome is preserved, while a failed decision write blocks the call.

## Verified, and not yet verified

- **Verified.** Both fixtures return identical status in all three modes, with and without the reviewer, and the same number of model calls. Seeded faults never reach `verified`. A real classification denial invokes the runner zero times and writes exactly one `allowed=0` row with no ledger node. Isolation probes against the Claude CLI come back clean on host-file read, directory listing and web fetch.
- **Not yet verified.** The Codex arm of the isolation probe is inconclusive because that CLI is quota-exhausted; the probe fails closed rather than reporting a false pass. Rerun `bash scripts/isolation_probe.sh codex` when quota returns before describing the both-host gate as met.
