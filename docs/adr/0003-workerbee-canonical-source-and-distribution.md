# ADR-0003: One canonical workerbee source

Status: proposed, 2026-09-06. NEEDS-OPERATOR: cross-project ownership and distribution change.

## Context

- This repo created `skills/workerbee/` at `0032c34` on 2026-09-05. The governance repo's working-tree copy has the same 11:54 timestamp. This repo added default polling at `d437ba7` at 12:16; the governance repo lacks it.
- The governance repo then renamed the copied skill to `workerbee` v1.2. This repo was `budget-mode-fleet` v1.1 (renamed to `workerbee` v1.1.1 on 2026-09-06 — frontmatter `name` now matches its own directory `skills/workerbee/` and the governance repo's name; metadata only, no protocol change). The governance repo v1.2 says the rename made no protocol change. Evidence favors accidental snapshot drift, not deliberate maturity stages.
- Both copies cite dead `~/Projects/workerbees` paths. The governance repo's copy adds another dead bridge path. Health-Wealth-Assistant records the same breakage.
- The governance repo's sync contract is outbound only: consumers pin it and pull; it never edits them. Its no-vendoring rule covers a **governance-repo-owned** skill copied **into a consumer tree**. It does not cover the governance repo importing an externally owned skill. Policy gap: **yes**.
- The governance repo already labels skills as vendored sources and lists upstream re-export ownership as unresolved. No inbound provenance, pin, or drift contract governs `workerbee`.

## Options

| Option | Actors | Defer/failure cost | Effort |
|---|---|---|---|
| A. This repo owns source; the governance repo re-exports an immutable commit pin (optionally named by a release tag) and verifies its digest | This-repo operator reconciles rename + polling + paths, versions, tests, publishes commit; the governance repo operator adds external-source contract, fetch/install path, drift check, removes hand-copy | Until done: wrong path and missing polling ship under a newer version. Poor fetch/auth design can break offline install | M: about 1 day across repos |
| B. Copy current source into the governance repo once and document the import | Both operators choose merged body/version; the governance repo operator copies it | Fixes today's delta only. Next source change silently repeats it | S: 1-3 hours |
| C. The governance repo keeps only a pointer document | The governance repo operator removes skill body and links pinned source; this-repo operator publishes stable locator | the governance repo discovery/install flows expect local skill content; pointer-only can make `workerbee` unavailable | S-M: 2-6 hours, plus installer redesign if distribution must remain |
| D. Accept two intentional forks | Both operators assign distinct names, owners, versions, dependencies, tests, changelogs | Until declared: users cannot tell which protocol/version is authoritative; dead paths remain. Ongoing double maintenance | M now; recurring |

Effort assumes no private-repo credential or installer constraint. Validate that before approval.

## Recommendation

Approve **A**. Pin the resolved commit SHA; use a tag only as a human release label. This preserves governance-repo distribution while keeping one editable source. Add a governance-repo inbound-source policy: external skills require owner, canonical URL, immutable pin, license/access rule, update owner, drift check, and local-patch prohibition. This extends rather than misapplies the downstream rule.

Do not call current copies intentional forks. Chronology and the governance repo's “no protocol change” note contradict that claim. Do not perform a one-time copy without an automated drift gate.

## Approval and investigation gates

1. **NEEDS-OPERATOR:** ratify this repo as canonical and decide whether the governance repo must distribute `workerbee` or may only catalog it.
2. Inventory live consumers and user-scope symlinks. Record which resolve through the governance repo versus this repo.
3. In this repo, merge the v1.2 rename/trigger improvements with Step 3a, replace dead paths, run skill benchmark/smoke checks, then choose the canonical version and commit. No tag until that body passes.
4. In a governance-repo branch, prototype SHA fetch/install under normal, offline, and private-auth conditions. Require digest equality with the pinned source and fail loud on unavailable content. A mutable branch or tag alone is not a pin.
5. Update the governance repo's MANIFEST entry and inbound-vendoring policy; remove its copied body only after the pinned path works. Update downstream dead-path references in separate, operator-approved repo changes.
6. Gate completion: one canonical editable body; `rg 'Projects/workerbees'` clean in active instructions; the governance repo install resolves the pinned SHA; source update produces a visible drift signal; rollback pin documented.

## Consequences

- Source fixes land once. The governance repo remains the ecosystem catalog/distribution authority, not source owner.
- The governance repo gains a missing inbound sync contract and some fetch complexity.
- This ADR authorizes no governance-repo or downstream writes. Operators must approve and execute those repo changes separately.
