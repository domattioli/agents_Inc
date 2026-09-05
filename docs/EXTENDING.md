# EXTENDING

- Reader
  - **Audience**
    - This is for adapting the system to a new vendor, task, or domain.
  - **Prerequisite**
    - Read `HOW-IT-WORKS.md` first.

## Rule zero

- Ownership
  - **Mechanism**
    - Put mechanism changes in `skills/codex-bridge/`.
  - **Judgment**
    - Put judgment changes in `skills/workerbee/SKILL.md`.
  - **Boundary check**
    - A routing table must not contain trust opinions, and a discipline document must not contain a retry loop.

## Add a model to an existing vendor

- Model addition
  - **Cost**
    - This is the cheapest change because it needs no new code.
  - **Existence check**
    - Verify the model on the account instead of trusting a table.

```bash
grep -E '^model' ~/.codex/config.toml
python3 -c "
import json;d=json.load(open('$HOME/.codex/models_cache.json'))
for m in d['models']:
    print(m.get('slug') or m.get('id'),'|',m.get('display_name'),
          '| effort:',[e['effort'] for e in m.get('supported_reasoning_levels',[])])
"
```

  - **Roster**
    - Add nickname, vendor, slug, exact dispatch command, tier, and use case to `skills/workerbee/SKILL.md` Step 1a.
  - **Price**
    - Add a price to `skills/codex-bridge/reference/prices.json` only when established.
    - Record free as `0.0`. Leave plan-based or unknown prices absent.
  - **Fallback**
    - Add the model to `reference/routing-policy.md` when it belongs in a chain.
  - **Nickname**
    - `astra`, `sol`, `terra`, and `luna` are account-specific ChatGPT codenames, not public names or Claude tiers.
    - Re-run step 1 on another machine before porting a nickname.

## Add a whole vendor

- Vendor addition
  - **Steps**
    - a.
      - Write a wrapper in `skills/codex-bridge/scripts/`, using `gask.sh` as the closest template. Read the key from a file or `.env`, never an argument, and never echo it. Map `--tier` from a friendly name to a real slug. Exit non-zero on API errors and write the verbatim error text to stderr. Log token counts through `usage_db.py`.
    - b.
      - Teach `route.sh` the backend name.
    - c.
      - Teach `agent.sh` to dispatch it.
    - d.
      - Add a roster row in `workerbee` Step 1a.
    - e.
      - Add prices to `prices.json` under the honesty rule.
    - f.
      - Add the limit, reset time, and exact failure string to `reference/budget-mode.md`. The quota record distinguishes a retryable failure from quota burning.
  - **Failure example**
    - `oask.sh` read the wrong key path, passed a file-exists check with placeholder content, and sent an empty bearer token that produced HTTP 401 without a clear key error.
  - **Required check**
    - Test with the key deliberately absent and deliberately wrong.

## Add a task class

- Task class
  - **Steps**
    - a.
      - Add it to `reference/routing-policy.md`.
    - b.
      - Give it an ORDERED chain because every backend has a ceiling.
    - c.
      - Explain the order in one clause. “Why this order” is a real column.
    - d.
      - For money or irreversible work, use numbered gates and `--sandbox read-only`, as required by `HOW-IT-WORKS.md`.

## Adapt to a new domain

- Domain adaptation
  - **Invariant**
    - The discipline stays domain-blind and defines process rather than subject matter.
  - **Task classes**
    - Replace classes such as “repo survey” and “stack trace analysis” with domain-specific classes.
  - **Verification**
    - Define what makes the result checkable before delegating. Code has tests, while other domains need an equivalent.
  - **Hard stops**
    - Write down what must never be delegated.
  - **Secrets**
    - Name the actual secret paths in every dispatch.
  - **Unchanged rules**
    - Keep tiering, the self-graded-gate ban, unknown≠zero, sandbox constraints, and fail-closed irreversible actions.

### Worked example: a law practice

Not an endorsement. A shape.

| task class | delegate? | verification |
|---|---|---|
| summarize a long deposition | yes, digest tier, 1M context | spot-check quotes against page numbers in source |
| extract every date + party from discovery | yes, cheap tier, high volume | re-run on a hand-labeled sample, count misses |
| find contradictions between two statements | yes, but as a CANDIDATE list only | read each candidate yourself |
| draft a client letter | draft only, never send | you are the signatory. delegate output is a first pass |
| anything filed, served, or sent to a client | **NO. HARD STOP.** | n/a |
| anything privileged leaving the machine | **NO. HARD STOP.** | n/a |

- Legal boundary
  - **Cloud transmission**
    - A cloud model call sends data away from the machine, and privilege obligations still apply to summaries.
  - **Dispatch rule**
    - Decide what may leave the machine, write it down, and put forbidden paths in every dispatch prompt.
  - **Verification**
    - Use a hand-labeled sample scored the same way every time because law has no test suite.

## Extensibility smells

| smell | why it costs |
|---|---|
| roster row with no dispatch command | next session reverse-engineers the vendor lookup by hand |
| price written `0.0` because unknown | confident wrong savings figures outlive the session |
| backend added, no failure-signal row | cannot distinguish retry-me from stop-burning-quota |
| task class with one backend, no chain | that backend hits its ceiling and the class dies |
| discipline copied into a second file | two sources of truth, they drift, the older one wins an argument someday |
| verifier the delegate can edit | grades intent, not result |

## Before you claim it works

- Verification checklist
  - **Wrapper failure**
    - Run it with the key absent. Expect a clear error and non-zero exit.
    - Run it with the key wrong. Expect a clear error, non-zero exit, and no silent empty result.
  - **Real call**
    - Run a one-shot. Output and token counts must land in `usage.db`.
  - **Routing**
    - `route.sh pick <class>` must return the backend.
  - **Cooldown**
    - Force cooldown and confirm the chain falls through to the next backend.
  - **Reporting**
    - `usage_report.sh` must show calls with a price or an explicit unknown.
  - **Count**
    - Six checks are required.
  - **History**
    - Skipping the two failure checks is how `oask.sh` shipped broken.
