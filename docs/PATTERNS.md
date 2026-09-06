# Delegation failure patterns

Observed in `agents_for_dummies` build sessions on 2026-09-05 and 2026-09-06. These are operating rules, not claims about every model or every delegation.

## 1. Verify the requested gate

- **Pattern: partial test run reported as completion**
  - Builders reported 9, 30, or 33 tests after being asked for full discovery.
  - Counter-rule: record the baseline; run the exact full-suite command locally; report its observed count.
  - Evidence: [DECISIONS lines 146–152](./DECISIONS.md#L146-L152).
- **Pattern: proof narrative contradicts the probe**
  - A three-table setup was described as proving a 42-table result.
  - Counter-rule: treat prose as a claim. Re-run the probe against the artifact.
  - Evidence: [DECISIONS line 146](./DECISIONS.md#L146).

## 2. Read assertions, not test names

- **Pattern: the named behavior is not exercised**
  - A “real policy denial” test patched the legacy pre-gateway path. Another denial test asserted success.
  - Counter-rule: trace the production call path and identify the assertion that would fail on regression.
  - Evidence: [DECISIONS lines 110–114](./DECISIONS.md#L110-L114).
- **Pattern: the patch target is unreachable**
  - A ledger-fault test patched the source module, while the gateway used its imported reference.
  - Counter-rule: prove the injected fault fires; then prove the expected boundary handles it.
  - Evidence: [DECISIONS line 118](./DECISIONS.md#L118).

## 3. Never weaken a gate to make it green

- **Pattern: changed fixture mechanics hide a mismatch**
  - Off mode used a different runner and lost its status assertion.
  - Counter-rule: hold inputs, runner, and assertions constant across a mode matrix.
  - Evidence: [DECISIONS lines 117–119](./DECISIONS.md#L117-L119).
- **Pattern: implementation contradicts its stated storage mode**
  - SQLite-only mode still wrote JSONL “for backward compatibility.”
  - Counter-rule: inspect external effects, including created files and audit rows, in every mode.
  - Evidence: [DECISIONS lines 154–158](./DECISIONS.md#L154-L158).

## 4. Test production wiring and missing paths

- **Pattern: correct unit, unreachable feature**
  - Governed doctor logic passed alone but its production caller omitted governance context.
  - Counter-rule: add one end-to-end fixture from the public entry point for every new wire.
  - Evidence: [DECISIONS lines 115–116](./DECISIONS.md#L115-L116).
- **Pattern: strong tests leave whole error classes untouched**
  - Three store defects mapped one-to-one to absent error-path tests.
  - Counter-rule: list failure modes before declaring completion; add a regression for every reproduced defect.
  - Evidence: [DECISIONS lines 148–153](./DECISIONS.md#L148-L153).

## 5. Bound the diff and validate reference data

- **Pattern: unrelated edits enter a scoped change**
  - Counter-rule: compare the final diff to the task file list. Explain or remove every extra path.
- **Pattern: plausible catalog data violates a semantic constraint**
  - Broker routes named the broker as model vendor, defeating same-vendor review lint.
  - Counter-rule: encode schema constraints as per-row tests; do not rely on plausible labels.
  - Evidence: [DECISIONS lines 141–145](./DECISIONS.md#L141-L145).

## 6. Prefer honest stops

- A stopped run with named failures is useful evidence. A green run after a removed requirement is not.
- “Cannot complete without violating the spec” is an acceptable result when it includes the failing command and reason.
- Evidence: [DECISIONS line 157](./DECISIONS.md#L157).

## Working checklist

1. Pin scope, baseline, command, and expected observable effect.
2. Exercise the production entry point.
3. Confirm each new test fails when its guarded behavior is broken.
4. Inspect mode-specific files, rows, calls, and statuses.
5. Read the diff and the assertions.
6. Report only locally observed results.
