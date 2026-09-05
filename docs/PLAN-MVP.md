# MVP build plan

Author: gpt-6-astra, high effort, read-only. Dispatched 2026-09-05.
Supervisor-verified citations: agent_runner.py:248, ask.sh:94, routing-policy.md:47,
DomI session-resume / verify-independently / plugin-install-with-vendored-fallback, DomI CLAUDE.md:126.
Unverified: the Claude `--bare` OAuth claim and all external URL citations.

**1. MVP CUT LINE**

Ship ranked -> reliable setup, evidence-backed document work, persistent memory, enforced governance.

| Priority | Ships | Tim payoff |
|---|---|---|
| P0 | Signed Mac bundle; transactional setup; doctor; repair; rollback | URL -> working installation without package-manager debugging |
| P0 | Source-linked analysis + drafting; lawyer/scientist/engineer | Useful first result |
| P0 | Claude/Codex CLI adapters; bounded delegation; independent verification | Subscription reuse; fewer unchecked claims |
| P0 | Per-workspace memory; provenance; checkpoint recovery | Next session continues without source reread |
| P0 | Provider/data policy; mode enforcement; draft-only outputs | Safe defaults survive session changes |
| P1 | Markdown, DOCX, text-bearing PDF input; Markdown/HTML/basic DOCX output | Common document workflow without terminal expertise |

**DEFERRED**

- Gemini/Mistral/OpenRouter; API-key tooling; price dashboards -> extra auth paths, wrong Tim routing. Subscription quota exhaustion remains explicit error.
- HTTP bridge; persistent model conversations -> daemon lifecycle + session contamination. Fresh CLI job per task.
- Codespaces; git/branch/milestone workflows -> account, identity, network dependencies without document payoff.
- Statusline; background watchers; mandatory MCP; plugin marketplace installation -> startup/config burden without first-win benefit.
- OCR; scanned/encrypted PDF processing; tracked-change fidelity; complex layout preservation -> difficult silent failures. Detect unsupported content; reject affected document explicitly.
- Autonomous filing/sending/publishing; legal research subscriptions; lab execution; engineering deployment -> separate authorization + verification problems.
- Agent fleets; recursive delegation; concurrent writers -> unnecessary recovery/state complexity.
- Long discipline narratives + speculative roadmap -> pre-MVP history/tag; roadmap issues in proposed separate `workerbees-lab` repo. Tim bundle excludes both.
- Keep repo runtime docs short. Build specs/tests remain maintainer-only; never packaged or auto-loaded.

**2. ARCHITECTURE**

Keep mechanism/judgment split -> add executable policy boundary. Prose chooses work; runtime controls permitted work + acceptance state.

`host agent -> workerbee judgment -> governed runner -> Claude/Codex adapter -> candidate -> verifier -> draft + receipt -> memory`

| Component | Owns | Boundary |
|---|---|---|
| Bootstrap/doctor | Installation transaction, compatibility, repair | No document/model judgment |
| Runner | Job state, deadlines, retries, artifact capture, policy checks | No self-reported success promotion |
| CLI adapters | Native subscription auth, invocation, event normalization | No routing or memory ownership |
| Document layer | Import, source hashes, page/paragraph anchors, export | No inference disguised as extraction |
| Judgment skills | Task decomposition, mode rubric, review | Cannot override runtime restrictions |
| Memory adapter | Scoped retrieval, accepted facts, checkpoints | Documents/memory never become executable policy |
| Governance | Provider allowlist, data scope, acceptance requirements | Enforced before dispatch + artifact promotion |

- Replace Codex transport -> direct CLI. Current runner calls `ask.sh`; wrapper posts localhost HTTP. Bridge removal requires adapter replacement, not file deletion alone. [runner:157](/Users/domattioli/Projects/workerbees/skills/codex-bridge/scripts/agent_runner.py:157), [ask.sh:94](/Users/domattioli/Projects/workerbees/skills/codex-bridge/scripts/ask.sh:94).
- Replace `succeeded` meaning -> `returned`; add `verified`, `needs-review`, `failed`, `interrupted`, `cancelled`. Current exit `0` promotes directly to `succeeded`. [runner:248](/Users/domattioli/Projects/workerbees/skills/codex-bridge/scripts/agent_runner.py:248).
- Cheap tier -> Codex, bounded prompt/output, tested account-supported model. No invented “free” price. Remove Gemini-first chains. [routing-policy:47](/Users/domattioli/Projects/workerbees/skills/codex-bridge/reference/routing-policy.md:47).
- One active job/workspace; delegation depth `1`; fresh process. Follow-up -> new job referencing selected prior evidence.
- Claude driver -> Codex worker, Claude supervisor review. Codex driver -> Codex worker, fresh Claude review for consequential claims; Codex supervisor owns acceptance.
- Transient failure -> one bounded retry. Auth/quota/policy failure -> stop. Interrupted dispatch -> reconcile process/result before retry.
- Worker receives selected text through stdin; document instructions treated as data. No arbitrary shell, file, web, MCP, connector, or recursive-agent tools. Runner writes results.
- Isolation -> tested adapter contract, including inherited config suppression. Read-only filesystem alone insufficient. Codex exposes shell/multi-agent/app controls; exact safe combination requires negative probes. [OpenAI config reference](https://learn.chatgpt.com/docs/config-file/config-reference).

**3. DEPENDENCY VERDICT**

| Component | Decision | Tim-install rationale + named fallback |
|---|---|---|
| projectmem | **DEPEND**, unmodified pinned package inside shipped runtime | Reuse memory persistence; eliminate Tim-side dependency resolution. Fallback: **last-good capsule + matching memory snapshot**; emergency bounded checkpoint export read-only |
| bindle | **REIMPLEMENT-MINIMAL** coordination ledger | Job ownership/state needed; git/branch/Obsidian bridge unnecessary. Fallback: **local recovery journal**, inspectable without bindle |
| spec-pressure-test | **FOLD IN**, maintainer spec gate | Preserve adversarial review without another runtime skill/install. Fallback: **versioned seven-category checklist**, no upstream fetch required |

- projectmem currently requires Python ≥3.10 plus Typer/MCP/watchdog. Ship private CPython + fully locked dependencies; no runtime `pip`, `uv`, Homebrew, or system Python. Larger download -> fewer installation failure points. [projectmem pyproject](https://raw.githubusercontent.com/riponcm/projectmem/main/pyproject.toml).
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

- Default mode -> `lawyer`; setup demonstration uses synthetic matter. Explicit user-selected mode overrides.
- Persist mode + schema version per workspace. Every job freezes mode/version, source set, policy version.
- Mode switch -> new job context; shared source catalog retained; derived conclusions rechecked against new rubric.
- Missing jurisdiction -> document summary allowed; jurisdiction-dependent conclusion blocked. Equivalent gating for missing study methods or engineering constraints.
- **Lawyer safety:** unknown/client-confidential data -> no model dispatch until matter-specific provider authorization recorded. Account login never implies client-data authorization.
- **Scientist safety:** human-subject, identifiable, embargoed, restricted data -> equivalent release gate. Mode selection never grants disclosure rights.
- **Engineer safety:** proprietary/export-restricted classification follows same deny-until-authorized rule. No operational execution.
- Mode switches cannot relax data policy. Source text cannot change mode, provider, permissions, or memory authority.
- Tim-facing drafts/help -> plain language. Agent orchestration -> compact fragments.

**5. SKILLS + HOOKS INVENTORY**

Exactly eight runtime skills; no independent plugin installation.

| Name | Purpose | Loading | Portability / source |
|---|---|---|---|
| `workerbees` | Entry contract; task routing; mandatory policy checks | Always, ≤180 tokens | Portable; distilled workerbee rules |
| `workerbees-setup` | Bootstrap, doctor, repair | On-demand, ≤500 | Portable; DomI fallback/verification pattern |
| `workerbees-delegate` | Narrow dispatch contract + result handling | On-demand, ≤400 | Portable; mechanism/judgment split |
| `workerbees-memory` | Resume, remember, correct, checkpoint | On-demand, ≤300 | Portable; DomI `session-resume` pattern |
| `workerbees-verify` | Predispatch checks + evidence receipt | Every result, on-demand, ≤450 | Portable; DomI `verify-independently`, adapted beyond code |
| `workerbees-lawyer` | Legal document rubric | Selected mode only, ≤300 | Portable; new domain pack |
| `workerbees-scientist` | Scientific document rubric | Selected mode only, ≤300 | Portable; new domain pack |
| `workerbees-engineer` | Engineering document rubric | Selected mode only, ≤300 | Portable; new domain pack |

- Always-loaded budget -> entry `180` + eight discovery descriptions `120` + active-mode safety header `80` + memory brief `400` = **780 estimated tokens/session**.
- Each always entry earns place -> operating contract, discoverability, disclosure restrictions, continuity. No other startup prose.
- Hook inventory -> **zero installed hooks**. Claude lifecycle hooks useful but client-specific; portable `start`, job checkpoint, `finalize` commands own lifecycle.
- Both clients -> generated instruction stubs + skill metadata from one canonical source. Claude `.claude/skills`; Codex `.agents/skills`. Shared body; separate discovery paths/client fields. [Claude skills](https://code.claude.com/docs/en/skills), [OpenAI skills](https://learn.chatgpt.com/docs/build-skills).
- MCP -> optional future adapter. No universal MCP assumption; no MCP setup in acceptance path.
- DomI take: `session-resume` -> bounded continuity; `verify-independently` -> checks before worker report; `plugin-install-with-vendored-fallback` -> explicit fallback + verification. [resume:45](/Users/domattioli/Projects/DomI/skills/session-resume/SKILL.md:45), [verify:72](/Users/domattioli/Projects/DomI/skills/verify-independently/SKILL.md:72), [fallback:39](/Users/domattioli/Projects/DomI/skills/plugin-install-with-vendored-fallback/SKILL.md:39).
- Convert principles into Workerbees functionality; no copied DomI skill trees or live sync dependency. DomI explicitly permits conversion; forbids downstream vendoring. [CLAUDE.md:126](/Users/domattioli/Projects/DomI/CLAUDE.md:126).
- Adapt deliberately: DomI verifier excludes documentation; its Stop hook measures command occurrence, not correctness. Neither ships unchanged. [skill:34](/Users/domattioli/Projects/DomI/skills/verify-independently/SKILL.md:34), [hook:8](/Users/domattioli/Projects/DomI/scripts/hooks/stop_verify_gap_guard.sh:8).

**6. INSTALL/BOOTSTRAP DESIGN**

**Primary deliverable -> signed/notarized Mac capsule**, Apple Silicon + Intel builds, private runtime + locked packages. No compiler/package manager on Tim machine.

1. Repo landing README -> single bounded setup contract; pinned release URL, digest, publisher identity, recovery instructions. Agent reads setup contract only.
2. Preflight -> supported macOS/CPU, network/TLS, disk, destination permission, CLI locations/versions. Resolve absolute executable paths; no shell-profile sourcing.
3. Download using Mac system tools -> private staging dir; verify release digest, signature, notarization. No `curl | sh`.
4. Run staged doctor -> runtime import check, both CLIs, native subscription auth, structured-output schema, isolation probes.
5. Create synthetic lawyer workspace -> memory initialization, source import, delegated extraction, draft, independent checks, restart/resume proof.
6. Activate -> atomic pointer switch to verified release. Register namespaced skill stubs using journaled edits; preserve existing files. Fresh client process validates discovery.
7. Emit setup receipt + open sample report. Install status becomes `READY` only after all checks.
8. New session -> same workspace/mode/checkpoint visible through either client. No git checkout required.

State -> `PREFLIGHT -> STAGED -> VERIFIED -> ACTIVE`; any failure -> explicit blocked state + recovery instruction. Existing active release remains usable.

| Failure | Exact proposed diagnostic | Recovery |
|---|---|---|
| No Homebrew/Python/uv/jq | No failure | Bundled runtime; none required |
| Git absent/no identity/GitHub 2FA | No failure | Public release download; no clone/commit/GitHub auth |
| Wrong shell/PATH | `WB_CLI_NOT_FOUND` | Search bounded supported install locations; save absolute path; unresolved -> name missing CLI |
| CLI needs login/2FA | `WB_AUTH_REQUIRED` | Open vendor login instructions; Tim completes login; rerun setup resumes |
| Gatekeeper/signature failure | `WB_RELEASE_UNTRUSTED` | Preserve active release; download verified release again; never disable Gatekeeper |
| Network/download interrupted | `WB_DOWNLOAD_INCOMPLETE` | Retry bounded download; no activation |
| Read-only sandbox/disk/TCC denial | `WB_INSTALL_PERMISSION_BLOCKED` | Name exact blocked operation/location; resume through host-approved access |
| Existing config conflict | `WB_CONFIG_CONFLICT` | Preserve original; provide focused conflict description; no overwrite |
| Unsupported CLI/security capability | `WB_CLI_UNSUPPORTED` | Name tested version requirement; retain staging + recovery receipt |

- Auth belongs exclusively to vendor CLIs. Workerbees never opens auth files, copies sessions, sources `.env`, or adds API credentials.
- Claude adapter -> native logged-in `-p` invocation; **exclude `--bare`**, which disables OAuth/keychain auth. Isolate inherited tooling with tested explicit config. [Claude programmatic mode](https://code.claude.com/docs/en/headless).
- Codex adapter -> `exec`, structured events, saved CLI auth. [OpenAI non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).
- Setup cannot bypass 2FA, OS consent, managed policy, or host sandbox. Success path unattended; blocked path loud + resumable. Never label blocked setup “complete.”
- Installation receipt -> release/client versions, phase, check IDs, repair command; no prompts/documents/account identifiers.
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

- Before dispatch -> supervisor defines requested fields, source coverage, critical claims, expected checks. Contract frozen outside worker control.
- Source importer -> per-page/paragraph coverage map; unreadable/empty/unsupported regions flagged. Extraction completeness never inferred from model confidence.
- Worker returns -> structured claims, exact excerpts, source anchors, uncertainty, candidate draft. No authority to set verified state.
- Deterministic verifier -> source hashes, quote matches, valid anchors, omitted required fields, arithmetic/unit checks, candidate/receipt hash binding.
- Supervisor semantic review -> every consequential claim against original excerpt + surrounding context; contradictions, missing qualifications, unsupported inference.
- Omission review -> source-driven pass independent of worker claims. Section coverage alone cannot prove completeness.
- Consequential output -> fresh other-vendor review with source + task rubric before viewing worker self-assessment. Agreement supports review; never proves truth.
- Three separate receipt results -> **source integrity**, **content review**, **human decision needed**. No universal green “legally correct.”
- Unresolved critical issue -> `needs-review`; useful draft retained, affected passages marked. Filing/sending never offered as verified automation.
- Tim report -> plain-language result, “checked X/Y claims,” unresolved items, clickable source excerpts, document/page links. No test-reading requirement.
- Example -> “12 quoted passages matched. Two interpretations need review. Clause 8 conflicts with Clause 3.” Each statement backed by machine check or named review record.
- Regression corpus -> domain-reviewed synthetic fixtures for all three modes; expected critical facts/omissions hidden from drafting worker.
- Mutation tests -> forged quote, missing exception, wrong denominator, stale source, swapped matter, fake success receipt, injected source instruction -> required failure.
- Release gate -> zero false accepts on critical seeded faults; all required fixture fields accounted for. Publish measured coverage; no extrapolated accuracy promise.
- Tim installation proof -> both vendors exercised; sample defect caught; clean draft produced; fresh process recalls checkpoint; interrupted setup rerun preserves state.
- Existing workerbee rule supplies core principle -> supervisor-owned checks, known-good + known-bad controls. [workerbee:191](/Users/domattioli/Projects/workerbees/skills/workerbee/SKILL.md:191).

**9. BUILD ORDER**

| Phase | Lands | Observable proof | Rough size |
|---|---|---|---|
| 1 | Signed pilot capsule; both CLI adapters; Markdown source -> cited brief; deterministic quote checks | URL -> useful sample brief on clean Mac; native subs work; injected quote rejected | 5–7 engineer-days |
| 2 | Transactional bootstrap, doctor, repair, rollback, config integration | Kill setup at each phase -> rerun recovers; no false READY | 5–7 days |
| 3 | Governed runner + three mode contracts; restricted tool surfaces | Mode-specific fixtures differ correctly; source injection cannot change policy | 4–6 days |
| 4 | Pinned projectmem adapter; scoped checkpoints; coordination ledger | Fresh Claude/Codex sessions resume; stale evidence invalidated; crash loses no accepted result | 4–6 days |
| 5 | PDF/DOCX import/export; full semantic review + evidence report | All domain fixtures + seeded critical defects satisfy release gate | 6–9 days |
| 6 | Fresh-Mac acceptance matrix; final docs/cut; release rehearsal | Tim-equivalent operator pastes URL, gets verified demo + resumed memory without technical intervention | 4–6 days |

- Phase 1 independently useful -> sourced Markdown analysis tool; labeled pilot, no claim of completed v1.
- Total -> **28–41 engineer-days**, plus domain-review/signing lead time.
- Before each implementation slice -> pressure-test state, invariants, ownership, concurrency, partial failure, composition, cardinality.
- Domain fixture authorship starts phase 1; not postponed until final QA.

**10. RISKS — RANKED**

| Rank | Specific failure on Tim Mac | Mitigation |
|---|---|---|
| 1 | CLI update breaks subscription auth, tool isolation, or event parsing | Tested capability matrix; synthetic auth/isolation probes; unsupported -> block; no credential copying/bare-mode shortcut |
| 2 | Fluent memo omits controlling exception or invents support | Source-driven omission review, exact anchors, independent semantic review, seeded faults, unresolved passages visible |
| 3 | Prompt injection or wrong workspace exposes confidential material | Explicit data authorization, tool-disabled workers, scope binding, no global fact inheritance, negative cross-matter probes |
| 4 | Gatekeeper/download/config failure leaves apparent installation | Signed capsule, staged activation, transaction journal, fresh-process check, single READY criterion |
| 5 | Memory migration/crash preserves stale conclusion or loses decision | Source hashes, single writer, idempotent journal, versioned snapshots, capsule+snapshot rollback |

**UNSURE -> evidence required**

- Native-subscription CLI isolation under inherited user config -> phase-1 tests on fresh + customized accounts. Unsupported secure configuration -> release blocker.
- Signing/notarization + private runtime behavior on both architectures -> downloadable quarantined-bundle trials; maintainer signing access required.
- projectmem integration compatibility/crash behavior -> pinned-package fixture replay, explicit-root tests, interrupted-write recovery. Source inspection establishes candidate viability, not passing integration.
- PDF/DOCX extraction quality -> representative lawyer/scientist/engineer documents with human-checked anchors; unsupported structures rejected.
- Semantic false-accept rate -> independent domain-labeled holdout corpus. Unknown until measured; setup success never substitutes for domain validation.
