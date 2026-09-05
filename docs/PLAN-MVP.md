# MVP build plan

Revised 2026-09-05 per docs/DECISIONS.md

Author: gpt-6-astra, high effort, read-only. Dispatched 2026-09-05.
Supervisor-verified citations: agent_runner.py:248, ask.sh:94, routing-policy.md:47,
DomI session-resume / verify-independently / plugin-install-with-vendored-fallback, DomI CLAUDE.md:126.
Verified 2026-09-05: `--bare` disables OAuth (claude 2.1.261, `--bare -p` -> "Not logged in"). Unverified: external URL citations.

**1. MVP CUT LINE**

Ship ranked -> reliable setup, evidence-backed work, persistent memory, enforced governance. Acceptance user -> Tim (lawyer, documents to cited brief) AND Dom (engineer/scientist tasks). Both day 1.

| Priority | Ships | Payoff |
|---|---|---|
| P0 | Marketplace where supported + git URL fallback; transactional setup; doctor; repair; rollback | Working installation through either supported route |
| P0 | Source-linked analysis + drafting; lawyer/scientist/engineer | Tim cited brief + Dom engineer/scientist acceptance from day 1 |
| P0 | Host: Claude Code AND Codex; one canonical skill source; bounded delegation | Either Host drives the same workflow |
| P0 | Required provider: Claude Code and Codex; subscription login | Missing Required provider blocks setup |
| P0 | Optional provider: Gemini, Mistral, OpenRouter free tiers; guided key setup | Missing key skips provider; never blocks setup |
| P0 | Per-workspace memory; provenance; checkpoint recovery | Next session continues without source reread |
| P0 | Spend cap; Workspace authorization; Mode enforcement; draft-only outputs | Hard $0/task; confidential optional-provider dispatch denied until explicit grant |
| P0 | Cost metric; all-frontier baseline; seeded-fault quality gate | Measured dollars per accepted task on both workflows |
| P1 | Markdown, DOCX, text-bearing PDF input; Markdown/HTML/basic DOCX output | Common document workflow without terminal expertise |

- Free -> zero incremental dollars per task; subscription-included or free-tier API key.
- Spend cap -> hard $0/task. No paid API path exists. Quota exhaustion -> pause job + tell user; no silent paid fallback.
- Setup -> browser to provider key page; hidden local terminal prompt writes user `.env`. Agent never sees key; key never enters chat or any model prompt.
- Workspace authorization -> explicit per-workspace grant permitting confidential inputs to reach Optional provider. Default denied; key presence never grants disclosure rights.
- Tier -> cheap / mid / frontier. Rules route; failed checks promote within Spend cap; Worker confidence never promotes. Model assignment -> probe + benchmark.
- Accepted task -> output reached Verified or Needs-review with retained draft. Cost metric -> dollars per accepted task against all-frontier baseline; quality floor zero false accepts on seeded faults.
- Measure Tim + Dom workflows. Report incremental dollars and subscription allocation separately. Subscription-only gains -> quota savings, not cash. No savings % before both workflows measured; zero-dollar baseline -> no percentage claim.

**DEFERRED**

- Paid API paths -> excluded. Price dashboards -> deferred; required Cost metric stays.
- HTTP bridge; persistent model conversations -> daemon lifecycle + session contamination. Fresh invocation per task.
- Codespaces; user git/branch/milestone workflows -> account, identity, network dependencies without document payoff. Git URL installation fallback stays.
- Statusline; background watchers; mandatory MCP -> startup/config burden without first-win benefit. Marketplace distribution stays where supported.
- OCR; scanned/encrypted PDF processing; tracked-change fidelity; complex layout preservation -> difficult silent failures. Detect unsupported content; reject affected document explicitly.
- Autonomous filing/sending/publishing; legal research subscriptions; lab execution; engineering deployment -> separate authorization + verification problems.
- Agent fleets; recursive delegation; concurrent writers -> unnecessary recovery/state complexity.
- Deterministic synthetic redaction -> far future. Never substitutes for Workspace authorization in MVP.
- Long discipline narratives + speculative roadmap -> pre-MVP history/tag; roadmap issues in proposed separate `workerbees-lab` repo. User distribution excludes both.
- Keep repo runtime docs short. Build specs/tests remain maintainer-only; never packaged or auto-loaded.

**2. ARCHITECTURE**

Keep mechanism/judgment split -> add executable policy boundary. Prose chooses work; runtime controls permitted work + acceptance state.

`Host -> Driver judgment -> governed runner -> Required provider / Optional provider adapter -> Worker candidate -> Verifier + Reviewer gates -> draft + receipt -> memory`

| Component | Owns | Boundary |
|---|---|---|
| Bootstrap/doctor | Installation transaction, compatibility, repair | No document/model judgment |
| Runner | Job state, deadlines, retries, artifact capture, policy checks | No self-reported success promotion |
| Provider adapters | Required provider subscription auth; Optional provider local key use; invocation, event normalization | No routing or memory ownership; no keys in model prompts |
| Document layer | Import, source hashes, page/paragraph anchors, export | No inference disguised as extraction |
| Judgment skills | Task decomposition, mode rubric, review | Cannot override runtime restrictions |
| Memory adapter | Scoped retrieval, accepted facts, checkpoints | Documents/memory never become executable policy |
| Governance | Spend cap, Workspace authorization, provider allowlist, data scope, acceptance requirements | Enforced before dispatch + artifact promotion |

- Replace Codex transport -> direct CLI. Current runner calls `ask.sh`; wrapper posts localhost HTTP. Bridge removal requires adapter replacement, not file deletion alone. [runner:157](/Users/domattioli/Projects/workerbees/skills/codex-bridge/scripts/agent_runner.py:157), [ask.sh:94](/Users/domattioli/Projects/workerbees/skills/codex-bridge/scripts/ask.sh:94).
- Replace `succeeded` meaning -> `returned`; Returned -> Worker process exited 0 and produced output, no correctness claim. Add `verified`, `needs-review`, `failed`, `interrupted`, `cancelled`; Verified requires Verifier + Reviewer gates. Current exit `0` promotes directly to `succeeded`. [runner:248](/Users/domattioli/Projects/workerbees/skills/codex-bridge/scripts/agent_runner.py:248).
- Tier -> cheap / mid / frontier; model assignment by probe + benchmark. Rules route; failed checks promote within Spend cap, never Worker confidence. Optional provider missing key -> skip. Free -> zero incremental dollars per task. [routing-policy:47](/Users/domattioli/Projects/workerbees/skills/codex-bridge/reference/routing-policy.md:47).
- One active job/workspace; delegation depth `1`; fresh process. Follow-up -> new job referencing selected prior evidence.
- Driver -> Host session dispatching a tool-free Worker. Reviewer -> different vendor than Worker, checks consequential claims against original sources. Verifier -> deterministic code. Driver owns acceptance after gates; every route obeys Spend cap + Workspace authorization.
- Transient failure -> one bounded retry. Quota exhaustion -> pause job + tell user; no paid API path. Auth/policy failure -> stop affected dispatch; missing Optional provider key skips provider. Interrupted dispatch -> reconcile process/result before retry.
- Worker receives selected text through stdin; document instructions treated as data. No arbitrary shell, file, web, MCP, connector, or recursive-agent tools. Runner writes results.
- Isolation -> tested adapter contract, including inherited config suppression. Read-only filesystem alone insufficient. Codex exposes shell/multi-agent/app controls; exact safe combination requires negative probes. [OpenAI config reference](https://learn.chatgpt.com/docs/config-file/config-reference).

**3. DEPENDENCY VERDICT**

| Component | Decision | Tim-install rationale + named fallback |
|---|---|---|
| projectmem | **DEPEND**, unmodified pinned package inside shipped runtime | Reuse memory persistence; eliminate Tim-side dependency resolution. Fallback: **last-good release + matching memory snapshot**; emergency bounded checkpoint export read-only |
| bindle | **REIMPLEMENT-MINIMAL** coordination ledger | Job ownership/state needed; git/branch/Obsidian bridge unnecessary. Fallback: **local recovery journal**, inspectable without bindle |
| spec-pressure-test | **FOLD IN**, maintainer spec gate | Preserve adversarial review without another runtime skill/install. Fallback: **versioned seven-category checklist**, no upstream fetch required |

- projectmem currently requires Python ≥3.10 plus Typer/MCP/watchdog. Ship private CPython + fully locked dependencies through marketplace + git URL routes; no runtime `pip`, `uv`, Homebrew, or system Python. Larger download -> fewer installation failure points. [projectmem pyproject](https://raw.githubusercontent.com/riponcm/projectmem/main/pyproject.toml).
- Disable projectmem hooks, watcher, global inheritance, history backfill, stack/structure scans, generated agent instructions, MCP config. Explicit initialization controls exist. [projectmem CLI](https://raw.githubusercontent.com/riponcm/projectmem/main/src/projectmem/cli.py).
- Workerbees adapter -> pinned library functions, explicit root. No agent-facing 17-tool catalog.
- Dependency upgrades -> maintainer CI, fixture replay, snapshot migration, signed release. Never resolve upstream “latest” during Tim setup.
- Memory failure -> preserve pending job + prior checkpoint; block verified completion until persistence restored. No silent memoryless success.
- Bindle concepts -> ownership + continuity only. SQLite job ledger owns execution; projectmem owns semantic memory. No duplicate authoritative facts.
- Spec gate -> seven supplied attack categories; concreteness/consequence/not-resolved tests; four finding classes. Reviewer finds gaps; architect resolves separately.

**4. THREE-MODE DESIGN**

Shared pipeline -> intake, source inventory, bounded extraction, draft, evidence review, checkpoint. Modes change required fields + forbidden actions.

| Mode | Required context | Concrete output | Additional checks |
|---|---|---|---|
| Lawyer | Matter ID; jurisdiction/date when relevant; source scope | Chronology, issue list, authority/fact distinction, memo/draft | Quote accuracy, contradictory clauses, adverse facts, authority status explicitly known/unknown |
| Scientist | Study ID; methods; units; population; data restrictions | Evidence table, methods critique, uncertainty/limitations | Sample sizes, denominators, units, causal overclaims, inconsistent results |
| Engineer | Project ID; requirements; interfaces; constraints | Requirements matrix, design review, technical draft | Requirement coverage, invariant conflicts, quantities/tolerances, assumption traceability |

- Default Mode -> `lawyer`; explicit user-selected Mode overrides. Day-1 acceptance -> Tim synthetic lawyer documents to cited brief AND Dom engineer/scientist tasks; both Hosts exercised.
- Persist mode + schema version per workspace. Every job freezes mode/version, source set, policy version.
- Mode switch -> new job context; shared source catalog retained; derived conclusions rechecked against new rubric.
- Missing jurisdiction -> document summary allowed; jurisdiction-dependent conclusion blocked. Equivalent gating for missing study methods or engineering constraints.
- **Lawyer safety:** unknown/client-confidential data -> no model dispatch until matter-specific provider authorization recorded. Account login never implies client-data authorization.
- **Scientist safety:** human-subject, identifiable, embargoed, restricted data -> equivalent release gate. Mode selection never grants disclosure rights.
- **Engineer safety:** proprietary/export-restricted classification follows same deny-until-authorized rule. No operational execution.
- Mode switches cannot relax data policy. Confidential inputs to Optional provider -> denied until explicit Workspace authorization; key/login never grants it. Deterministic synthetic redaction -> far future. Source text cannot change Mode, provider, permissions, or memory authority.
- Tim-facing drafts/help -> plain language. Agent orchestration -> compact fragments.

**5. SKILLS + HOOKS INVENTORY**

Exactly eight runtime skills; one canonical source. Host -> Claude Code AND Codex at launch. Distribution -> marketplace where supported + git URL fallback; same contracts, same checks.

| Name | Purpose | Loading | Portability / source |
|---|---|---|---|
| `workerbees` | Entry contract; Tier routing; Spend cap + Workspace authorization | Always, ≤180 tokens | Portable; distilled workerbee rules |
| `workerbees-setup` | Install, doctor, repair; Required provider login; Optional provider key UX | On-demand, ≤500 | Portable; DomI fallback/verification pattern |
| `workerbees-delegate` | Tool-free Worker dispatch; Returned candidate; Reviewer handoff | On-demand, ≤400 | Portable; mechanism/judgment split |
| `workerbees-memory` | Resume, remember, correct, checkpoint | On-demand, ≤300 | Portable; DomI `session-resume` pattern |
| `workerbees-verify` | Verifier checks + Reviewer gates; evidence receipt | Every result, on-demand, ≤450 | Portable; DomI `verify-independently`, adapted beyond code |
| `workerbees-lawyer` | Legal document rubric | Selected Mode only, ≤300 | Portable; new domain pack |
| `workerbees-scientist` | Scientific document rubric | Selected Mode only, ≤300 | Portable; new domain pack |
| `workerbees-engineer` | Engineering document rubric | Selected Mode only, ≤300 | Portable; new domain pack |

- Always-loaded budget -> entry `180` + eight discovery descriptions `120` + active-Mode safety header `80` + memory brief `400` = **780 estimated tokens/session**.
- Each always entry earns place -> operating contract, discoverability, disclosure restrictions, continuity. No other startup prose.
- Hook inventory -> **zero installed hooks**. Claude lifecycle hooks useful but client-specific; portable `start`, job checkpoint, `finalize` commands own lifecycle.
- Both Hosts -> generated instruction stubs + skill metadata from one canonical source. Claude Code `.claude/skills`; Codex `.agents/skills`. Shared body; separate discovery paths/client fields. [Claude skills](https://code.claude.com/docs/en/skills), [OpenAI skills](https://learn.chatgpt.com/docs/build-skills).
- START-HERE -> caveman-lite + nested-notes first draft; then write-like-scientist pass. Human-skimmable; no AI slop. Cover both Hosts, both Acceptance users, Required provider login, Optional provider skip/key path, Spend cap, Workspace authorization, recovery.
- Key handling -> local setup code only. Agent opens provider key page; user types key into hidden local terminal prompt; code writes user `.env`. No key in agent-visible output, logs, receipts, chat, or model prompts; no agent reads user `.env`.
- MCP -> optional future adapter. No universal MCP assumption; no MCP setup in acceptance path.
- DomI take: `session-resume` -> bounded continuity; `verify-independently` -> checks before Worker report; `plugin-install-with-vendored-fallback` -> explicit fallback + verification. [resume:45](/Users/domattioli/Projects/DomI/skills/session-resume/SKILL.md:45), [verify:72](/Users/domattioli/Projects/DomI/skills/verify-independently/SKILL.md:72), [fallback:39](/Users/domattioli/Projects/DomI/skills/plugin-install-with-vendored-fallback/SKILL.md:39).
- Convert principles into Workerbees functionality; no copied DomI skill trees or live sync dependency. DomI explicitly permits conversion; forbids downstream vendoring. [CLAUDE.md:126](/Users/domattioli/Projects/DomI/CLAUDE.md:126).
- Adapt deliberately: DomI verifier excludes documentation; its Stop hook measures command occurrence, not correctness. Neither ships unchanged. [skill:34](/Users/domattioli/Projects/DomI/skills/verify-independently/SKILL.md:34), [hook:8](/Users/domattioli/Projects/DomI/scripts/hooks/stop_verify_gap_guard.sh:8).

**6. INSTALL/BOOTSTRAP DESIGN**

**Primary distribution -> marketplace where supported + git URL fallback.** Same pinned release + canonical skills for Claude Code and Codex. Private runtime + locked packages -> install payload shared by both routes.

1. START-HERE -> bounded setup contract; marketplace entry where supported, git URL fallback, pinned revision/digest, publisher identity, recovery instructions. Agent reads setup contract only.
2. Preflight -> supported macOS/CPU, network/TLS, disk, destination permission, Host/CLI locations + versions; selected distribution route + runtime requirements. Resolve absolute executable paths; no shell-profile sourcing.
3. Stage pinned release -> supported marketplace installer or git URL fallback. Verify revision/digest + release provenance; journal owned changes; preserve existing config. No `curl | sh`.
4. Required provider -> Claude Code AND Codex; native subscription login. Doctor checks both CLIs, auth, structured-output schema, tool isolation. Missing Required provider -> blocked + resumable.
5. Optional provider -> Gemini, Mistral, OpenRouter free tiers. Offer skip or guided key acquisition. Agent opens provider key page; user types key into hidden local terminal prompt; local code writes permission-restricted user `.env`. Key never visible to agent or model. Missing key -> skip provider, continue setup.
6. Enforce Spend cap -> only subscription-included/free-tier routes; no paid API path. Unproven zero-dollar route -> disable Optional provider; required route failure -> block. Probe quota pause + user notice; probe confidential Optional provider denial without Workspace authorization.
7. Synthetic acceptance -> Tim lawyer documents to cited brief AND Dom engineer/scientist tasks from day 1. Exercise both Hosts + Required providers; memory initialization, source import, Worker candidate, Verifier + Reviewer gates, seeded defect, restart/resume. Optional providers tested when configured; absent keys never block READY.
8. Activate -> atomic pointer switch to verified release. Register namespaced skill stubs using journaled edits; preserve existing files. Fresh Host processes validate discovery from canonical source.
9. Emit setup receipt + sample reports. `READY` only after required checks. Next session -> same workspace/Mode/checkpoint through either Host; user git identity never required for document work.

State -> `PREFLIGHT -> STAGED -> VERIFIED -> ACTIVE`; required-check failure -> explicit blocked state + recovery instruction. Existing active release remains usable. Optional-provider skip is recorded, never setup failure. Installation `VERIFIED` names a phase; task Verified still requires Verifier + Reviewer gates.

| Failure | Exact proposed diagnostic | Recovery |
|---|---|---|
| Marketplace unsupported/unavailable | `WB_MARKETPLACE_UNAVAILABLE` | Use pinned git URL fallback; same setup + acceptance checks |
| Git missing on fallback route | `WB_GIT_REQUIRED` | Guide supported Git installation; resume pinned checkout; no user commit identity required |
| Runtime/dependency missing | `WB_RUNTIME_REQUIRED` | Retrieve locked private runtime payload; doctor proves readiness |
| Wrong shell/PATH | `WB_CLI_NOT_FOUND` | Search bounded supported install locations; save absolute path; unresolved Required provider -> block |
| Required provider needs login/2FA | `WB_AUTH_REQUIRED` | Open vendor login instructions; user completes login; rerun setup resumes |
| Optional provider key missing/invalid | `WB_OPTIONAL_PROVIDER_SKIPPED` | Skip provider; offer hidden local key prompt; continue required setup |
| Quota exhausted | `WB_QUOTA_EXHAUSTED` | Pause job + tell user; retain checkpoint; no paid fallback |
| Confidential Optional provider dispatch lacks Workspace authorization | `WB_WORKSPACE_AUTH_REQUIRED` | Deny dispatch; explicit per-workspace grant required; login/key never grants it |
| Release provenance/signature failure | `WB_RELEASE_UNTRUSTED` | Preserve active release; retrieve verified release; never disable Gatekeeper |
| Network/download interrupted | `WB_DOWNLOAD_INCOMPLETE` | Retry bounded download; no activation |
| Read-only sandbox/disk/TCC denial | `WB_INSTALL_PERMISSION_BLOCKED` | Name exact blocked operation/location; resume through Host-approved access |
| Existing config conflict | `WB_CONFIG_CONFLICT` | Preserve original; provide focused conflict description; no overwrite |
| Unsupported CLI/security capability | `WB_CLI_UNSUPPORTED` | Name tested version requirement; retain staging + recovery receipt |

- Required provider auth -> vendor CLIs only. Never open auth files or copy sessions. Optional provider key -> local setup code writes user `.env`; local adapter reads only its configured credential, never sources shell code or includes credentials in Worker stdin/model prompts. Redact errors; exclude `.env` from source import, memory, git, logs, receipts.
- Claude Code adapter -> native logged-in `-p`; **exclude `--bare`** (verified: skips keychain -> "Not logged in"). Isolation via explicit `--disallowedTools` list + `--setting-sources ""` + `--strict-mcp-config` (positive probe: shell request -> `NO_EXEC`; `--tools ""` alone insufficient). Full negative-probe matrix -> Phase 1. [Claude programmatic mode](https://code.claude.com/docs/en/headless).
- Codex adapter -> `exec`, structured events, saved CLI auth. [OpenAI non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).
- Optional provider adapters -> tool-free Worker invocations, same evidence gates; deny confidential inputs without Workspace authorization; hard $0 eligibility checked before dispatch. No redaction bypass.
- Setup cannot bypass 2FA, OS consent, managed policy, or Host sandbox. Required human login/key/consent steps -> explicit + resumable; automated remainder continues. Never label blocked setup “complete.”
- Installation receipt -> release/client versions, distribution route, phase, check IDs, Optional provider enabled/skipped status, repair command; no keys, prompts, documents, account identifiers.
- Benchmark receipt -> Cost metric against all-frontier baseline for Tim + Dom; incremental dollars + subscription allocation separate; zero false accepts on seeded faults. No savings % until both workflows measured; zero-dollar baseline -> no percentage claim.
- Update/uninstall -> journaled; backups retained; uninstall removes owned integration only. Matters preserved.

**7. MEMORY DESIGN**

- Installation -> `~/Library/Application Support/Workerbees/`.
- Default matter storage -> private directory there, outside application repo; source copies/imports explicit.
- Per workspace -> `.projectmem/` semantic memory; `.workerbees/` jobs, source catalog, policy, receipts, checkpoints.
- Remember -> user decisions/preferences, task objective, accepted findings + source anchors, unresolved questions, rejected approaches, next action.
- Global memory -> interface preferences only. Matter facts never inherited globally.
- Facts -> `observed`, `inferred`, `disputed`, `superseded`; verification status separate. Unknown never becomes zero/false.
- Session-start read -> **400 estimated tokens**: scope/mode `60`, objective/next action `80`, decisions `100`, source-linked findings `100`, blockers/freshness `60`.
- Brief hard cap -> deterministic field budgets; overflow -> omitted-item count + on-demand retrieval. Safety fields never truncated.
- Source ingestion -> content hash, parser version, stable anchors, extraction warnings. Unchanged hash -> cached extraction; changed hash -> dependent findings stale.
- Retrieval -> task + source IDs; relevant snippets only. No full source reread unless evidence changed or spot-check requires original.
- Never model-read raw events, transcripts, job logs, entire historical summaries, unrelated matters, or complete source corpus.
- Runner sole writer -> per-workspace lock; idempotent event IDs; append/checkpoint validation. Both hosts submit through same adapter.
- Save after each accepted task/decision; no dependence on session-end hook. Crash -> pending journal reconciled before next operation.
- Corrections append superseding records. Forget/export -> explicit workspace operation; no claim to erase vendor-side histories.

**8. VERIFICATION**

**Tim receives inspectable evidence, not “tests passed.”**

- Before dispatch -> Driver defines requested fields, source coverage, critical claims, expected checks. Contract frozen outside Worker control.
- Source importer -> per-page/paragraph coverage map; unreadable/empty/unsupported regions flagged. Extraction completeness never inferred from model confidence.
- Worker returns -> structured claims, exact excerpts, source anchors, uncertainty, candidate draft. No authority to set verified state.
- Verifier -> deterministic code: source hashes, quote matches, valid anchors, omitted required fields, arithmetic/unit checks, candidate/receipt hash binding. Never a model.
- Reviewer -> model invocation from a different vendor than Worker; every consequential claim against original excerpt + surrounding context; contradictions, missing qualifications, unsupported inference. Driver owns acceptance after gates.
- Omission review -> source-driven pass independent of worker claims. Section coverage alone cannot prove completeness.
- Consequential output -> fresh other-vendor review with source + task rubric before viewing worker self-assessment. Agreement supports review; never proves truth.
- Three separate receipt results -> **source integrity**, **content review**, **human decision needed**. No universal green “legally correct.”
- Verified -> Returned output passed Verifier + Reviewer gates. Needs-review -> Verified checks passed but unresolved critical issue remains for human; draft retained, affected passages marked. Failed gates never count as Accepted task. Filing/sending never offered as verified automation.
- Tim report -> plain-language result, “checked X/Y claims,” unresolved items, clickable source excerpts, document/page links. No test-reading requirement.
- Example -> “12 quoted passages matched. Two interpretations need review. Clause 8 conflicts with Clause 3.” Each statement backed by machine check or named review record.
- Regression corpus -> domain-reviewed synthetic fixtures for all three modes; expected critical facts/omissions hidden from drafting worker.
- Mutation tests -> forged quote, missing exception, wrong denominator, stale source, swapped matter, fake success receipt, injected source instruction -> required failure.
- Release gate -> zero false accepts on seeded faults; all required fixture fields accounted for. Publish measured coverage; no extrapolated accuracy promise.
- Acceptance user proof -> Tim documents to cited brief AND Dom engineer/scientist tasks, day 1; both Hosts + Required providers exercised; sample defect caught; clean draft produced; fresh process recalls checkpoint; interrupted setup rerun preserves state; missing Optional provider keys never block.
- Existing workerbee rule supplies core principle -> supervisor-owned checks, known-good + known-bad controls. [workerbee:191](/Users/domattioli/Projects/workerbees/skills/workerbee/SKILL.md:191).

**9. BUILD ORDER**

| Phase | Lands | Observable proof | Rough size |
|---|---|---|---|
| 1 | Marketplace where supported + git URL pilot; both Hosts + Required providers; Optional provider key/skip path; Spend cap + Workspace authorization; Tim + Dom fixtures | Both day-1 workflows run; native subs work; hidden key stays local; quota pauses; unauthorized disclosure + injected quote rejected | 5–7 engineer-days, re-estimate expanded scope |
| 2 | Transactional bootstrap, doctor, repair, rollback, config integration | Kill setup at each phase -> rerun recovers; no false READY | 5–7 days |
| 3 | Governed runner + three mode contracts; restricted tool surfaces | Mode-specific fixtures differ correctly; source injection cannot change policy | 4–6 days |
| 4 | Pinned projectmem adapter; scoped checkpoints; coordination ledger | Fresh Claude/Codex sessions resume; stale evidence invalidated; crash loses no accepted result | 4–6 days |
| 5 | PDF/DOCX import/export; full semantic review + evidence report | All domain fixtures + seeded critical defects satisfy release gate | 6–9 days |
| 6 | Fresh-Mac acceptance matrix; START-HERE editorial passes; Cost metric vs all-frontier baseline; release rehearsal | Tim + Dom workflows pass through both Hosts + distribution routes; guided human steps clear; memory resumes; zero false accepts on seeded faults | 4–6 days, re-estimate expanded scope |

- Phase 1 independently useful -> sourced Markdown analysis tool; labeled pilot, no claim of completed v1.
- Prior estimate -> **28–41 engineer-days**; re-estimate D1–D12 scope before commitment. Implementation starts Phase 1 only on CEO “build.”
- Before each implementation slice -> pressure-test state, invariants, ownership, concurrency, partial failure, composition, cardinality.
- Domain fixture authorship starts phase 1; not postponed until final QA.

**10. RISKS — RANKED**

| Rank | Specific failure on Tim Mac | Mitigation |
|---|---|---|
| 1 | CLI update breaks subscription auth, tool isolation, or event parsing | Tested capability matrix; synthetic auth/isolation probes; unsupported -> block; no credential copying/bare-mode shortcut |
| 2 | Fluent memo omits controlling exception or invents support | Source-driven omission review, exact anchors, independent semantic review, seeded faults, unresolved passages visible |
| 3 | Prompt injection or wrong workspace exposes confidential material | Explicit data authorization, tool-disabled workers, scope binding, no global fact inheritance, negative cross-matter probes |
| 4 | Marketplace/git URL/download/config failure leaves apparent installation | Pinned verified release, route-specific preflight, staged activation, transaction journal, fresh-process check, single READY criterion |
| 5 | Memory migration/crash preserves stale conclusion or loses decision | Source hashes, single writer, idempotent journal, versioned snapshots, release+snapshot rollback |

**UNSURE -> evidence required**

- Native-subscription CLI isolation under inherited user config -> phase-1 tests on fresh + customized accounts. Unsupported secure configuration -> release blocker.
- Marketplace support + git URL fallback on both Hosts; runtime behavior on both Mac architectures -> route-specific fresh-install/recovery trials. Signed/notarized runtime payload, if used -> quarantined-download trial.
- projectmem integration compatibility/crash behavior -> pinned-package fixture replay, explicit-root tests, interrupted-write recovery. Source inspection establishes candidate viability, not passing integration.
- PDF/DOCX extraction quality -> representative lawyer/scientist/engineer documents with human-checked anchors; unsupported structures rejected.
- Semantic false-accept rate -> independent domain-labeled holdout corpus. Unknown until measured; setup success never substitutes for domain validation.
