# ADR-0003: One canonical workerbee source

Status: proposed, 2026-09-06. NEEDS-OPERATOR: cross-project ownership and distribution change.

## Context

- This repo created `skills/workerbee/` at `0032c34` on 2026-09-05. DomI's working-tree copy has the same 11:54 timestamp. This repo added default polling at `d437ba7` at 12:16; DomI lacks it.
- DomI then renamed the copied skill to `workerbee` v1.2. This repo was `budget-mode-fleet` v1.1 (renamed to `workerbee` v1.1.1 on 2026-09-06 — frontmatter `name` now matches its own directory `skills/workerbee/` and DomI's name; metadata only, no protocol change). DomI v1.2 says the rename made no protocol change. Evidence favors accidental snapshot drift, not deliberate maturity stages.
- Both copies cite dead `~/Projects/workerbees` paths. DomI's copy adds another dead bridge path. Health-Wealth-Assistant records the same breakage.
- DomI's sync contract is outbound only: consumers pin DomI and pull; DomI never edits them (`/Users/domattioli/Projects/DomI/CLAUDE.md:120-124`). Its no-vendoring rule covers a **DomI-owned** skill copied **into a consumer tree** (`CLAUDE.md:126`). It does not cover DomI importing an externally owned skill. Policy gap: **yes**.
- DomI already labels skills as vendored sources (`/Users/domattioli/Projects/DomI/MANIFEST.md:5`) and lists upstream re-export ownership as unresolved (`README.md:59-62`). No inbound provenance, pin, or drift contract governs `workerbee`.

## Options

| Option | Actors | Defer/failure cost | Effort |
|---|---|---|---|
| A. This repo owns source; DomI re-exports an immutable commit pin (optionally named by a release tag) and verifies its digest | This-repo operator reconciles rename + polling + paths, versions, tests, publishes commit; DomI operator adds external-source contract, fetch/install path, drift check, removes hand-copy | Until done: wrong path and missing polling ship under a newer version. Poor fetch/auth design can break offline install | M: about 1 day across repos |
| B. Copy current source into DomI once and document the import | Both operators choose merged body/version; DomI operator copies it | Fixes today's delta only. Next source change silently repeats it | S: 1-3 hours |
| C. DomI keeps only a pointer document | DomI operator removes skill body and links pinned source; this-repo operator publishes stable locator | DomI discovery/install flows expect local skill content; pointer-only can make `workerbee` unavailable | S-M: 2-6 hours, plus installer redesign if distribution must remain |
| D. Accept two intentional forks | Both operators assign distinct names, owners, versions, dependencies, tests, changelogs | Until declared: users cannot tell which protocol/version is authoritative; dead paths remain. Ongoing double maintenance | M now; recurring |

Effort assumes no private-repo credential or installer constraint. Validate that before approval.

## Recommendation

Approve **A**. Pin the resolved commit SHA; use a tag only as a human release label. This preserves DomI distribution while keeping one editable source. Add a DomI inbound-source policy: external skills require owner, canonical URL, immutable pin, license/access rule, update owner, drift check, and local-patch prohibition. This extends rather than misapplies the downstream rule.

Do not call current copies intentional forks. Chronology and DomI's “no protocol change” note contradict that claim. Do not perform a one-time copy without an automated drift gate.

## Approval and investigation gates

1. **NEEDS-OPERATOR:** ratify this repo as canonical and decide whether DomI must distribute `workerbee` or may only catalog it.
2. Inventory live consumers and user-scope symlinks. Record which resolve through DomI versus this repo.
3. In this repo, merge the v1.2 rename/trigger improvements with Step 3a, replace dead paths, run skill benchmark/smoke checks, then choose the canonical version and commit. No tag until that body passes.
4. In a DomI branch, prototype SHA fetch/install under normal, offline, and private-auth conditions. Require digest equality with the pinned source and fail loud on unavailable content. A mutable branch or tag alone is not a pin.
5. Update DomI's MANIFEST entry and inbound-vendoring policy; remove its copied body only after the pinned path works. Update downstream dead-path references in separate, operator-approved repo changes.
6. Gate completion: one canonical editable body; `rg 'Projects/workerbees'` clean in active instructions; DomI install resolves the pinned SHA; source update produces a visible drift signal; rollback pin documented.

## Consequences

- Source fixes land once. DomI remains the ecosystem catalog/distribution authority, not source owner.
- DomI gains a missing inbound sync contract and some fetch complexity.
- This ADR authorizes no DomI or downstream writes. Operators must approve and execute those repo changes separately.
