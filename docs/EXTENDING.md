# EXTENDING

Caveman ultra. Reader = whoever adapts this to a new vendor, task, or domain.

Read `HOW-IT-WORKS.md` first. This file assumes it.

## Rule zero

Mechanism changes go in `skills/codex-bridge/`. Judgment changes go in `skills/workerbee/SKILL.md`. Never both in one file.

Symptom you broke it: a routing table with opinions about trust, or a discipline doc with a retry loop in it.

## Add a model to an existing vendor

Cheapest change. No new code.

1. verify it EXISTS on this account — do not trust a table, including this one:
```bash
grep -E '^model' ~/.codex/config.toml
python3 -c "
import json;d=json.load(open('$HOME/.codex/models_cache.json'))
for m in d['models']:
    print(m.get('slug') or m.get('id'),'|',m.get('display_name'),
          '| effort:',[e['effort'] for e in m.get('supported_reasoning_levels',[])])
"
```
2. add a row to the roster table in `skills/workerbee/SKILL.md` Step 1a: nickname, vendor, slug, exact dispatch command, tier, when-to-use
3. price it in `skills/codex-bridge/reference/prices.json` ONLY if you can establish the price. Free → `0.0` explicitly. Plan-based or unknown → leave absent. Never `0.0` to make a total look complete.
4. add it to the fallback chain in `reference/routing-policy.md` if it belongs in one

Vendor nicknames are account-specific. `astra`/`sol`/`terra`/`luna` are this ChatGPT account's codenames, not public names, and NOT Claude tiers. Do not port a nickname to another machine without re-running step 1.

## Add a whole vendor

1. write a wrapper in `skills/codex-bridge/scripts/`. Copy `gask.sh` — closest template. Contract it must honor:
   - key read from a file or `.env`. Never an argument. Never echoed.
   - `--tier` maps friendly name → real slug
   - non-zero exit on API error, error text on stderr verbatim
   - token counts logged via `usage_db.py`
2. teach `route.sh` the backend name
3. teach `agent.sh` to dispatch it
4. roster row in `workerbee` Step 1a
5. prices in `prices.json`, per the honesty rule above
6. quota-shape row in `reference/budget-mode.md` — what its limit is, when it resets, the EXACT failure string it emits

Step 6 is the one people skip. Without the real failure signal you cannot tell "retry this" from "stop, you are burning quota".

**Trap:** `oask.sh` broke exactly here. Copied the sibling convention of reading `~/.codex-bridge/<vendor>-key`, but the real key lived elsewhere. The file EXISTED with placeholder content, so the file-exists guard passed and the "key not found" error never fired. Result: empty bearer token, HTTP 401, silent. Test with the key deliberately absent AND deliberately wrong — not just present.

## Add a task class

1. name it in `reference/routing-policy.md`
2. give it an ORDERED fallback chain, not one backend. Every backend has a ceiling.
3. justify the order in one clause. "Why this order" is a real column, not decoration.
4. if the class touches money or anything irreversible → numbered gates + `--sandbox read-only`, per `HOW-IT-WORKS.md`

## Adapt to a new domain

The discipline is domain-blind on purpose. `workerbee` has opinions about process, none about your problem. That is why it ports.

What changes per domain:
- **task classes.** Yours will not be "repo survey" and "stack trace analysis".
- **verification.** The hardest part and the only one nobody can hand you. For code it is a test suite. For a domain with no compiler you must define what "checkable" means BEFORE delegating, or you get fluent unfalsifiable output.
- **what must never be delegated.** Write it down as a hard stop, not a habit.
- **secret paths.** Name the actual files in every dispatch.

What does NOT change: tiering, the self-graded-gate ban, unknown≠zero, sandbox gotchas, fail-closed on irreversible actions.

### Worked example — a law practice

Not an endorsement. A shape.

| task class | delegate? | verification |
|---|---|---|
| summarize a long deposition | yes, digest tier, 1M context | spot-check quotes against page numbers in source |
| extract every date + party from discovery | yes, cheap tier, high volume | re-run on a hand-labeled sample, count misses |
| find contradictions between two statements | yes, but as a CANDIDATE list only | read each candidate yourself |
| draft a client letter | draft only, never send | you are the signatory. delegate output is a first pass |
| anything filed, served, or sent to a client | **NO. HARD STOP.** | n/a |
| anything privileged leaving the machine | **NO. HARD STOP.** | n/a |

Last two rows are the real ones. A cloud model call is data leaving your machine. Privilege and confidentiality obligations do not care that it was "just a summary". Decide what may leave BEFORE wiring anything up, write it as a hard stop, and put the forbidden paths in every dispatch prompt.

Verification for law is the unsolved half. There is no test suite. Nearest workable substitute: a hand-labeled sample you built yourself, scored the same way every time, so a delegate's claim has something to be wrong against.

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

- run the wrapper with key absent → clear error, non-zero exit
- run with key wrong → clear error, non-zero exit, no silent empty result
- run a real one-shot → output + token counts land in `usage.db`
- `route.sh pick <class>` → returns your backend
- force the backend into cooldown → chain falls through to next
- `usage_report.sh` → your calls appear with a price or an explicit unknown

Six checks. Skipping the two failure ones is how `oask.sh` shipped broken.
