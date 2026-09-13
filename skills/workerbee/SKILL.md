---
name: workerbee
version: 1.1.3
benchmark: unverified_delegate_claims_accepted_per_session
description: Supervision discipline for running work through a multi-vendor fleet of delegate models in budget mode — capability tiering, flash-tier triage of delegate reports, supervisor-owned verification harnesses, and the honesty rules that keep delegated work trustworthy. Use when orchestrating codex/gemini/mistral/OpenRouter delegates, when a delegate reports a gate as passing, or when deciding which tier a task belongs to. Pairs with `codex-bridge` (that skill is the dispatch mechanism; this one is the judgment about using it). Caveman-style output.
---

# workerbee

Discipline for supervising a fleet of cheaper models while staying the
accountable party for their output. Covers capability tiering, report
triage, verification, and the honesty rules that keep a delegated result
worth believing. Replaces per-session re-derivation of "should I trust
this delegate's GREEN?" — a question that cost three false accepts in one
session before these rules existed.

This skill is judgment, not plumbing. The dispatch machinery lives in
`codex-bridge` (`~/Projects/workerbees`).

## Metadata

- **Category**: Fleet Orchestration / Delegation
- **Use Case**: Supervising codex/gemini/mistral/OpenRouter delegates in budget mode; deciding tier placement; deciding whether a delegate's reported gate can be believed
- **Dependencies**: `codex-bridge` skill for actual dispatch (`agent.sh`, `gask.sh`, `mask.sh`, `oask.sh`). No scripts of its own
- **Scope**: Supervision discipline only. Transport, routing, retries, timeouts and job state belong to `codex-bridge`

## When to Use

- Orchestrating work across non-Claude delegate models in budget mode
- A delegate reports a gate GREEN and you must decide whether to accept it
- Choosing which capability tier a task belongs to, or whether to escalate
- Building a dispatch prompt for a delegate or a review agent
- Computing or displaying cost/savings across a mixed free-and-paid fleet

## When NOT to Use

- Single-model work with no delegation — there is no fleet to supervise
- Wiring up transport, provider routing, retries or job state — that is
  `codex-bridge`, and duplicating it here is how the fleet ended up with
  two parallel dispatch paths in the first place
- Domain logic of any kind. This skill has opinions about process, none
  about your problem

## Failure Mode This Solves

Documented in session `33338e35-4ce9-43db-8cf0-624adf37e136` (2026-09-04/05).

A supervisor delegating heavily accepts delegate self-reports because they
arrive formatted as evidence. In one session three separate GREEN gates
were false: an alignment gate that printed the delegate's intended array
rather than its rendered output (claimed columns `0 12 44 91 124`, measured
`0 12 49 122 214 329 446`); a harness that passed while row labels silently
vanished from live output because it measured 4 boundaries on rows holding
7 items; and a timing claim of `0.664s` that measured `0.461s`. None were
dishonesty — each was a delegate grading its own work. Separately, a null
price coerced to zero inflated a reported savings figure ~29x, from a
defensible `$1.15` to `$33.06`.

## Protocol

### Step 1: Place the task on the capability ladder

Two vendors, one ladder. Pick the tier the task needs.

| tier | Anthropic | OpenAI | use for |
|---|---|---|---|
| ultra | fable | astra | hardest reasoning, last resort |
| flagship | opus | sol | orchestration, adversarial review, gates |
| workhorse | sonnet | terra | implementation, supervising a pair |
| flash | haiku | luna | triage, mechanical edits, high volume |
| bottom rung | — | oss / free | one-shot text, drafts, sounding boards, well-scoped small coding (high volume of small diffs, never a large or architecturally significant change) |

Coding at flash/bottom-rung is scope-gated, not banned: small, narrow, high-volume jobs only. A task needing scope/design judgment is workhorse+, dispatch it there.

Under a mandate, dispatch Codex rows via `agent.sh submit --backend codex --model <slug> --mandate <run_id> --role <rung>`; bare `codex exec` is stateless and must not be used for Executive/Supervisor re-engagement (spec-010, `skills/codex-bridge/SKILL.md` `agent.sh` mandate flags).

**Scout = mode, not tier.** Recon before real dispatch (does X exist / what
shape / worth it). Text-only recon -> free grunt (OpenRouter free, gemini
cheap/digest, mistral cheap, gpt-5.4-mini). Recon needs tools (walk repo,
read tree, run cmd) -> Grunt rung only: haiku or luna; free grunts have no
tools. Never workhorse+ as scout -> if it needs sonnet/terra it is the
work, dispatch it properly. Scout writes nothing, returns finding only,
report unverified -> re-derive before acting. Ledger: node with edge_type
`probes`, no lineage row -> never a spawn ancestor. Canon: CONTEXT.md
Scout rows + DECISIONS D28.

**Escalate on evidence, not on a hunch.** A problem is not ultra-tier
because it feels hard. It is ultra-tier because a flagship actually failed
at it, twice, and you can say how.

**Ultra tier has a token floor.** Measured: a one-word reply from
`gpt-6-astra` cost 3,181 tokens. So an ultra model is expensive per call
regardless of task size. Never make it a default, and never make it
discover context you already have — pre-load verified facts into its
prompt so it spends its tokens on judgment instead of exploration.

**Vendor nicknames are not Claude names.** `astra`/`sol`/`terra`/`luna` are
OpenAI codenames for this operator's Codex account, unrelated to the
Claude `Agent` tool's `model` param (`opus`/`sonnet`/`haiku`/`fable`).
Failure mode this closes: told to "fan out an astra", the orchestrator
checked the `Agent` tool, found no `astra` model, and reported "astra
isn't available" — wrong; astra is a GPT model dispatched through `codex`,
not through `Agent`. Session `33338e35-4ce9-43db-8cf0-624adf37e136`
2026-09-05. Do not assume a vendor nickname is a Claude tier without
checking Step 1a first.

#### Step 1a: MODEL ROSTER — nickname → slug → dispatch command

Verified against this machine 2026-09-05 (`which`, config files — do not
assume, re-verify per Step 1b if stale). Only vendors with a working
credential or CLI on this machine are listed; do not invent a row for a
vendor that isn't wired up here.

| nickname | vendor | slug | dispatch | tier | when-to-use |
|---|---|---|---|---|---|
| astra | OpenAI (Codex, this acct) | `gpt-6-astra` | `codex exec -m gpt-6-astra -c model_reasoning_effort=<level> --skip-git-repo-check "<prompt>"` | ultra | hardest reasoning, last resort. Effort `ultra` self-delegates — see Step 1c |
| sol | OpenAI (Codex, this acct) | `gpt-5.6-sol` | `codex exec -m gpt-5.6-sol -c model_reasoning_effort=<level> --skip-git-repo-check "<prompt>"` | flagship | orchestration, adversarial review, gates |
| terra | OpenAI (Codex, this acct) | `gpt-5.6-terra` | `codex exec -m gpt-5.6-terra -c model_reasoning_effort=<level> --skip-git-repo-check "<prompt>"` | workhorse | implementation, supervising a pair |
| luna | OpenAI (Codex, this acct) | `gpt-5.6-luna` | `codex exec -m gpt-5.6-luna -c model_reasoning_effort=<level> --skip-git-repo-check "<prompt>"` | flash | triage, mechanical edits, high volume. No `ultra` effort exists for this slug — floor is `max`, so luna cannot self-delegate |
| fable | Anthropic | n/a — `Agent` tool | `Agent(model="fable", ...)` | ultra | Claude-side hardest reasoning, last resort |
| opus | Anthropic | n/a — `Agent` tool | `Agent(model="opus", ...)` | flagship | Claude-side orchestration, adversarial review, gates |
| sonnet | Anthropic | n/a — `Agent` tool | `Agent(model="sonnet", ...)` | workhorse | Claude-side implementation |
| haiku | Anthropic | n/a — `Agent` tool | `Agent(model="haiku", ...)` | flash | Claude-side triage, mechanical edits |
| gemini digest | Google Gemini, free tier | `gemini-3.8-flash` | `skills/codex-bridge/scripts/gask.sh --tier digest "<prompt>"` | workhorse-ish | 1M-context bulk digest of one large blob (logs, transcripts) |
| gemini cheap | Google Gemini, free tier | `gemini-flash-lite-latest` | `skills/codex-bridge/scripts/gask.sh --tier cheap "<prompt>"` | flash | high-volume shallow triage |
| gemini deep | Google Gemini, free tier | `gemini-3.1-pro-preview` | `skills/codex-bridge/scripts/gask.sh --tier deep "<prompt>"` | — | **verify quota before use**: `limit: 0` on this account as of 2026-09-02, i.e. currently unusable |
| mistral cheap | Mistral API | `ministral-3b-latest` | `skills/codex-bridge/scripts/mask.sh --tier cheap "<prompt>"` | flash | mechanical transform |
| mistral code | Mistral API | `codestral-latest` | `skills/codex-bridge/scripts/mask.sh --tier code "<prompt>"` | workhorse | code review/critique. Devstral not exposed on this key; codestral is the substitute |
| mistral deep | Mistral API | `mistral-large-latest` | `skills/codex-bridge/scripts/mask.sh --tier deep "<prompt>"` | workhorse | research-style questions |
| openrouter free | OpenRouter, free-tier models only | model id from `curl https://openrouter.ai/api/v1/models` | `skills/codex-bridge/scripts/oask.sh "<prompt>"` | bottom rung | one-shot text/drafts. Hard-coded spend guard refuses non-free models — operator rule is spend nothing on OpenRouter |

Bridge scripts (`gask.sh`/`mask.sh`/`oask.sh`) live in `skills/codex-bridge/scripts/` in this repo, alongside this skill. Prefer `agent.sh submit --backend <b> --wait "<prompt>"` over calling a wrapper directly (see `## CLI` section below) — it gives a job id and a saved `result.json`.

Gemini/Mistral/OpenRouter have no vendor-marketed codenames like astra/luna — dispatch by tier name, not nickname. Only OpenAI's Codex-account models are branded with person-names in this operator's `models_cache.json`; treat that as this-account-specific, not a public naming convention.

#### Step 1b: Discover models at runtime — don't hardcode, verify

Nicknames, slugs, and available effort levels can change per Codex-account
config. Before trusting this table on a machine or account you have not
just verified, run:

```bash
# What's the current default model + effort for this Codex account?
grep -E '^model' ~/.codex/config.toml
# → model = "gpt-6-astra"
# → model_reasoning_effort = "medium"

# Full roster this account can see, with per-model reasoning levels:
python3 -c "
import json
d = json.load(open('$HOME/.codex/models_cache.json'))
for m in d['models']:
    slug = m.get('slug') or m.get('id') or ''
    levels = [e['effort'] for e in m.get('supported_reasoning_levels', [])]
    print(slug, '|', m.get('display_name'), '| effort levels:', levels)
"

# Is a vendor CLI/credential actually present before you write a roster row for it?
which codex; which gemini; which mistral
ls ~/.codex-bridge/*-key 2>/dev/null   # gemini-key, openrouter-key present = wired
ls ~/.config/devstral 2>/dev/null       # mistral agent creds present = wired
```

Never document a vendor row from memory or from a prior session's table —
re-run this before dispatching to a nickname you have not already
confirmed exists on this account, this session.

#### Step 1c: Reasoning effort is an operator cost decision, not a model default

Effort (`low|medium|high|xhigh|max|ultra` for Codex models) is a **separate
axis from model/tier choice** and is never inferred by the orchestrator.
Distinct failure closed here: told explicitly "I do NOT want it on ultra
effort," the orchestrator had already dispatched at `ultra` unprompted —
same session, immediately after the astra/luna misidentification.

- Default effort when the operator hasn't stated one: `medium`. Do not
  round up "hard-sounding" tasks to `high`/`xhigh`/`max` without being told.
- `ultra` effort is a hard opt-in, not a tier default, because on models
  that support it (astra/sol/terra — not luna, which caps at `max`) it
  means **"maximum reasoning with automatic task delegation"**: the model
  spawns its own sub-agents and burns budget outside your control loop.
  Never select `ultra` effort unless the operator names it explicitly in
  this dispatch. A prior session using `ultra` is not standing consent for
  this one.
- State the chosen effort level back to the operator when it's anything
  above `medium` — silent escalation is the failure mode, not the token
  cost alone. (Superseded upward by Step 11 MUST 9: effort is now stated
  on every dispatch, at every level.)
- Do not conflate this with the capability-ladder "ultra" **tier** in Step
  1 (fable/astra as a *model choice*). Tier and effort are independent
  dials; a `flash`-tier model can in principle run at high effort, and a
  `ultra`-tier model can run at low effort. Name both when you report a
  dispatch: "astra @ medium effort", not just "astra".

### Step 2: Never accept a self-graded gate

The single most expensive failure. A delegate reports GREEN, and the
evidence it prints is its own **intent** rather than its own **result**.

Observed, verbatim: a delegate reported alignment GREEN with
`COLUMN INDICES: 0 12 44 91 124`. Those were the values from the array it
had planned. Measuring the rendered output gave
`row1: [0, 12, 49, 122, 214, 329, 446]` — nothing aligned, and lines ran
2-3x wider than claimed.

**Fix: the supervisor owns the verifier.**

- Write the harness yourself. Put it outside the delegate's workspace.
- State in the dispatch: DO NOT EDIT IT.
- Require the harness's full output plus its exit code in the report.
- Say explicitly: a claim without harness output is automatically RED.
- Self-test the harness both ways before you trust it — prove it reports
  GREEN on a known-good input and RED on a known-bad one. An unfalsifiable
  harness is worse than none.

**A passing harness is still not proof.** A harness only measures what it
can see. One passed while the delegate emitted 4 cell markers for rows
that held 7 items — the coarse boundaries lined up, the items inside them
did not. Check that the harness's granularity matches the claim's
granularity. Instrument the output yourself when the two might differ.

### Step 3: Verify the delegate's claims, cheaply

Do not re-do the work. Do re-run the check.

Worth the tool call every time:
- re-run the delegate's own verification command
- diff the claimed number against the measured one
- confirm the file it says it edited actually changed

Real catches from one session: a reported 0.664s that measured 0.461s; a
"gap closed" report that left the single most-used model still unpriced;
row labels silently dropped from a live UI while the alignment gate stayed
green. None of these were dishonesty. All were a delegate grading itself.

### Step 3a: Poll every dispatch. Default on.

A dispatch you are not polling is a dispatch that can hang silently. A
long-running delegate that has died is indistinguishable from one that is
thinking, and the difference is invisible until you go looking.

**Poll by default, on every dispatch that outlives one tool call.**

```
scripts/poll.sh --pid-match <pat> --log <stderr> --out <stdout> \
                --stall 480 --interval 60 --max 5400
scripts/poll.sh --once ...        # single check
```

**Token-smart by construction: it reports STATE, never content.** One short
line per state CHANGE, nothing at all on a tick where nothing changed.
States: `RUNNING` / `QUIET` / `RESUMED` / `DONE` / `DIED` / `TIMEOUT`.

Piping a delegate's log into the supervisor's context spends exactly the
tokens delegation was meant to save. The supervisor needs to know THAT it is
working, not WHAT it is saying — read the output once, at the end.

`DIED` is the state that pays for the rest: process gone, output empty. Never
infer completion from a process exiting. **Exit 0 means returned, not
verified** — keep those two states distinct or a crashed job reads as a
success.

To actually watch a job, use `scripts/watch.sh` in another pane. That stream
goes to a human's eyes, not into a context window — which is also the only
progress signal available to an operator who cannot read a test.

Self-test the poller both ways before trusting it, same bar as any harness
(Step 2): prove it says `DONE` on a finished job and `DIED` on a killed one.

### Step 4: Triage delegate reports through a flash model

In budget mode, route completed delegate reports to a standing flash-tier
interlocutor. Forward the report **verbatim** via message; surface only
what it marks ESCALATE.

Give delegates a matching instruction: tag operator-facing items
`NEEDS-OPERATOR`, phrased as a direct question. Everything else is
absorbed.

Honest caveat: the reliable saving is the operator's **attention**, not
always tokens — the triage agent costs tokens too, and you still read a
report to forward it. It pays off clearly on long reports and high volume.

Add supervisor context when you forward. You often know that an escalation
is really a sandbox nit, or that a defect is structural and fixable. Saying
so keeps triage from escalating noise.

### Step 5: Keep unknown distinct from zero

The costliest quiet bug is a null coerced to zero.

Observed: savings math read `(cost_of(.) // 0)`. A genuinely free model and
a model of **unknown** price became arithmetically identical, and unknown
usage silently inflated reported savings by ~29x — `$33.06` where the
defensible figure was `$1.15`.

- make free explicit (price it `0.0`) so absent can mean unknown
- exclude unknown from the sum rather than counting it as zero
- carry a companion field for what was excluded, and mark the headline
  figure partial when it is (`~$1.15+?`)
- **do not price a thing you cannot establish.** Plan-based access is
  neither free nor per-token; a `0.0` there is the same lie in the other
  direction. Absent is the honest answer.

### Step 6: Feed stateless buddies real source

Free-tier models see only your prompt. Given a *description* of a
function, they will invent a plausible one that does not exist — this
burned a whole collaboration round.

Paste verbatim source, real sample rows, actual command output. And:
**buddy output is never evidence.** Verify anything you keep against the
real system yourself, with a citation.

Expect provider failure. Observed verbatim:

```
ask_openrouter: API error: Upstream error from Nvidia: Service temporarily overloaded
ask_gemini: API error: This model is currently experiencing high demand.
ask_mistral: API error: Not enough capacity available for this request, please retry later.
```

Fail over across the family. Never stall on one dead provider.

### Step 7: Know the sandbox gotchas

- A delegate under `workspace-write` has **no network**. HTTP buddies fail
  with `Could not resolve host: ...`. Fix:
  `-c 'sandbox_workspace_write.network_access=true'`.
- The same sandbox blocks `.git/index.lock`, so delegates **cannot
  commit**. Expect `Operation not permitted`. Have the delegate report
  `BLOCKED-SANDBOX` and land the commit yourself.
- `--skip-git-repo-check` is required outside a git repo.
- Read-only sandbox is the cheapest way to enforce a review-only scope. Do
  not rely on the model honoring "do not edit" when the sandbox can
  guarantee it.

### Step 8: Fail closed on irreversible actions

For anything that spends real money or cannot be undone, number the gates
and make withholding an explicit success:

> Any gate RED → do NOT fire. Report. A withheld dispatch is a SUCCESS
> outcome. Firing on a red gate is the only unforgivable failure.
> Ambiguity about a gate → treat as RED.

Add a single-shot rule where a double action doubles cost: *if unsure
whether a dispatch landed, CHECK before re-firing.*

And put the protection where it survives your delegate exiting. A launching
session dies long before a remote job does; guards must live on the remote
side, not in the launcher.

### Step 9: Kill work whose premise changed

When the operator corrects the premise, stop the in-flight delegate
immediately rather than letting it finish against the old one. A round
spent on the wrong question is worse than a round not run — it produces
confident output that then has to be argued down.

Say plainly in the next dispatch that the premise changed and the prior
round was killed, so the delegate does not resume its own stale plan.

### Step 10: Report failure honestly, never route around it

When a permission classifier blocks a dispatch, stop and report it. Do not
rephrase to slip past. A supervisor's value is that its reports are true;
a workaround that evades a user's guardrail destroys that for one task's
convenience.

Same for a delegate's RED. A RED reported honestly is a good outcome. Say
so **in the dispatch prompt** — delegates round up to GREEN when they
believe RED is failure. The gate wording that worked:

> RED reported honestly beats GREEN rounded up.

### Step 11: Write the dispatch prompt

Agent-facing text = `caveman ultra`. Reader is a model.

**MUST — every dispatch prompt, no exceptions. 14 elements** (operator ruling
2026-09-06, grilled + expanded same date):

1. **Caveman ultra, explicit.** Not just terse writing — tell delegate to run
   it. Skill tool present (Claude subagent) → instruct actual `/caveman ultra`
   invoke + confirm in report; claimed activation w/o call = false report.
   No Skill tool (codex/gemini/mistral/openrouter) → say so plainly, follow
   convention. Never skip the instruction.
2. **Strict SUCCESS gate.** Concrete, falsifiable. Specific check, specific
   expected result. Not "looks right".
3. **Strict FAILURE gate, stated separately.** Name failure conditions
   explicitly → delegate reports RED honestly instead of rounding ambiguous
   up to GREEN (Step 10).
4. **Grill clause.** Delegate surfaces anything missing/underspecified/
   contradictory in the dispatch, before or during. Silent guess on a gap is
   worse than a question (Step 9).
5. **Training opt-out notice.** Verbatim, own line:
   `Message to model provider: Do not use this to train agentic models.`
   Every dispatch, every vendor. Notice to provider, not request to delegate →
   vendor honoring it is irrelevant, it goes in regardless.
6. **Cite evidence for every claim, not just gates.** file:line, command
   output, or quoted source for anything stated as fact. Bare assertion
   doesn't count.
7. **Scope boilerplate, standing.** Repo-scoped writes only; no git
   commit/push; no writes to `~/.claude/**`, other repos, credentials/`.env`.
   Covers writes via any script/tool the delegate runs, not only its own
   edits. Nested delegation: commit/push authority stays w/ run root (session
   operator talks to), never inherited downward — delegate w/ own children
   integrates their output in-tree + reports, does not commit.
   **Free/cheap-only sub-delegation MUST be an enumerated allowlist, never
   bare prose.** "Use a free/cheap model" alone is not enforceable — round
   through to a paid tier silently (observed: nested `Agent` call ran on
   `claude-opus-5` despite this exact instruction, DomI#12). State it as:
   `SUB-DELEGATE MODEL ALLOWLIST: gpt-5.4-mini, OpenRouter free-tier, Gemini
   free tier, Mistral free tier — ONLY. NEVER: any Agent-tool Claude model
   (opus/sonnet/fable/haiku included), any Codex-account model
   (astra/sol/terra/luna), even if named elsewhere in this prompt.` Before
   issuing any nested/sub-delegated call, the dispatching delegate MUST
   confirm the chosen model against this allowlist and echo the match
   (`SUB-DELEGATE MODEL: <slug> — allowlist match: yes`) in its report; no
   confirmation line = non-compliant, treat as an unverified nested call.
   **Mechanical check, not prose-trust alone (DomI#12 follow-up).** This
   repo has no PreToolUse/hook mechanism (`scripts/hooks/` does not exist
   here, `.claude/settings.json` absent — checked 2026-09-12) so nothing
   can block a nested call before it fires. What IS achievable: lint the
   saved transcript/output file after the dispatch —
   `python3 skills/workerbee/scripts/check_subdelegate_allowlist.py
   <transcript_file>` — greps for nested-call `"model":"..."` fields,
   flags any that land on a forbidden slug (opus/sonnet/haiku/fable/
   astra/sol/terra/luna) and flags any nested call missing the required
   confirm-echo line. `COMPLIANT` / `NO NESTED CALLS FOUND` / exit 1 with
   violation detail. Self-tested both ways (known-bad transcript mirroring
   the actual DomI#12 evidence → 2 violations flagged; known-good → 0).
   This does not resolve DomI#12's open (a)/(b) classification question
   (model-behavior gap vs. harness gap) — it only makes the drop
   detectable after the fact instead of trusting the prose alone.
8. **Confidentiality/data-classification tag.** State classification of
   content the delegate handles (e.g. public / confidential).
9. **Explicit effort level, every dispatch, default medium.** State chosen
   reasoning effort always — not only above medium (raises Step 1c's old bar
   to unconditional). **Default = medium, every vendor**, unless operator
   names a different level for that specific dispatch; a prior dispatch's
   level is not standing consent. Codex: `low|medium|high|xhigh|max|ultra`
   (Step 1c; `ultra` Codex-only, self-delegates, opt-in, never default;
   luna floor = `max`, no `ultra`). Claude/Anthropic:
   `low|medium|high|xhigh|max` — no `ultra` this vendor. `Agent`-tool
   transport has no per-dispatch effort param → prompt says so, never
   silently skips: `EFFORT: effort control unavailable on this transport;
   intended level = medium (or <operator-named level>)`. Delegate
   self-calibrates depth to that level + echoes it in report.
10. **Second-opinion / wheel-spin justification, paid vendors only.** Second
    opinion or escalation to a **paid/subscribed** vendor (any Anthropic
    `Agent`-tool model; any Codex-account model — astra/sol/terra/luna) MUST
    name which trigger fired + why. Triggers defined ONCE in `CLAUDE.md` labor
    rule ("Failed check — definition of record"), not restated here.
    Promotion/escalation triggers: (a) 2 failed checks, same (task, delegate);
    (b) provider quota pause = 1 failed attempt; (c) Lead assigns w/ recorded
    gate reason. Second opinion (same rung, the pair, blind — not promotion):
    Executive reason = conflicting results | irreversible act | risk eval.
    **Free-tier vendors** (openrouter free, gemini free, mistral free,
    `gpt-5.4-mini` free routes) need none — no cost to justify against.
    No trigger applies → `SECOND-OPINION JUSTIFICATION: not applicable —
    <reason>`. Explicit N/A satisfies; silence does not.
11. **Delegation-capable plans name model + gates per task.** Delegate asked
    for a plan (speckit encouraged) that permits further delegation → plan
    MUST state, per task, which model/tier does it + that task's own success +
    failure criteria. Same discipline propagated one level down, so a
    sub-delegate can't skip it either. Not a plan →
    `PLAN CONTRACT: not applicable — deliverable is not a plan`.
12. **Report shape: scope left out, assumptions, files created.** Report MUST
    state (a) anything incomplete or out of full scope even if every gate
    passed → closes silent scope-narrowing; (b) starting assumptions +
    whether/why any changed; (c) every file created. **Minimal file creation
    is the standing default** — new file only when the task requires one.
13. **Edit hygiene: surgical over full-rewrite.** Minimize tokens spent
    editing, all else equal. Default to targeted edit over rewriting a whole
    existing file whenever the end result is identical. Full-rewrite fine when
    it genuinely is the smaller/clearer diff (short file, or nearly everything
    changes). Bans rewriting when a smaller edit gets the identical result,
    not rewriting outright.
14. **Lesson-learned handling: relay up the chain, never sideways.** Delegate
    surfacing a finding w/ canon-doc implications (`CLAUDE.md`/`CONTEXT.md`/
    `docs/DECISIONS.md`/any `SKILL.md`/constitution) tags it
    `LESSON-CANDIDATE` in its report, not buried in prose. Relays exactly one
    rung up (Grunt→Workhorse→Orchestrator→Executive), never skipping. Each
    receiving rung either drops it (state why) or relays further. Before it
    reaches Executive, a scout check (Step 1 Scout mode) must confirm it
    doesn't already exist in canon + doesn't contradict canon — whoever
    relays is responsible for that check having happened somewhere in the
    chain. **Only Executive (fable/astra) presents a survivor to the
    operator** — one concise paragraph: lesson, evidence, scout's
    dedup/contradiction result, target canon file. Executive may land
    small/minor doc fixes itself; anything material needs operator sign-off,
    same bar as amending `CLAUDE.md` or the constitution. Not a GitHub issue —
    relay up the rung chain, not file sideways (operator ruling 2026-09-06).

These 14 fold into, not replace, the shape below. 10 + 11 conditional; the
other twelve unconditional. Compliant = each of the 14 present as content or
explicit N/A line; a missing element is non-compliant either way.
**No other element has an N/A out — 10 and 11 are the ONLY two of the 14
that can be satisfied by an explicit-N/A line instead of real content.**
Root cause closed: DomI#10 — a cross-repo dispatch used none of the 14,
bare task description only, from a session with no local reason to know
this contract existed. Paste-and-tick before sending ANY dispatch prompt,
any delegate/rung/vendor, this repo or a session dispatching into it:

```
[ ] 1 caveman ultra: Claude subagent -> Skill-tool invoke instructed + confirm-in-report REQUIRED, no N/A out. Non-Claude vendor (codex/gemini/mistral/openrouter, genuinely no Skill tool) -> explicit no-Skill-tool statement only
[ ] 2 success gate stated, falsifiable
[ ] 3 failure gate stated, separate from success
[ ] 4 grill clause present
[ ] 5 training opt-out line verbatim
[ ] 6 evidence-citation instruction present
[ ] 7 scope boilerplate + (if sub-delegating) free-tier allowlist
[ ] 8 confidentiality/classification tag present
[ ] 9 effort level stated explicitly
[ ] 10 second-opinion justification OR explicit N/A
[ ] 11 plan contract OR explicit N/A
[ ] 12 report-shape instruction (scope-left-out, assumptions, files created)
[ ] 13 edit-hygiene instruction present
[ ] 14 lesson-candidate handling instruction present
```

Any unticked box (other than 10/11 with a stated N/A) → prompt is
non-compliant, do not send it.

**Cross-repo dispatch, external session (DomI#10 gap — honest limit, not a
claimed fix).** DomI#10's actual root cause: a session working in a
*different* repo (DomI), dispatching work about an agents_Inc issue, never
read agents_Inc's `CLAUDE.md` — it had no local reason to know this
contract existed. This repo cannot reach into another repo's session and
force a read; no such enforcement mechanism exists here (no hook, no CI
gate that runs against external repos). The only thing achievable from
this side: make the contract self-contained and say plainly, in the
canonical source (`CLAUDE.md` § Delegation prompt contract), that any
session — this repo or another — dispatching work that touches an
agents_Inc issue/task MUST fetch and apply this section first. Paste-and-
tick block above is written to be copy-pasted whole into a dispatch prompt
from anywhere, needing no other agents_Inc file open. **This does not
close the gap for a session that never thinks to look** — that half of
DomI#10 stays open; a real fix would need the *dispatching* repo (DomI, or
whichever originates the call) to add its own check, which is out of this
repo's control.

Include, roughly this order:
1. ROLE, one line
2. REPORTING CHAIN — who receives report, what escalates
3. VERIFIED STATE — facts already established, marked do-not-re-derive
4. THE TASK + what is explicitly out of scope
5. HARD CONSTRAINTS (MUST 7) — read-only paths, no commits, no paid calls,
   secrets
6. CAVEMAN ULTRA (MUST 1) — invoke-and-confirm, or state-no-skill
7. CLASSIFICATION TAG (MUST 8) + EFFORT LEVEL (MUST 9)
8. SUCCESS GATES (MUST 2) — numbered, measurable, evidence required
9. FAILURE GATES (MUST 3) — explicit; RED honest beats GREEN rounded up
10. SECOND-OPINION JUSTIFICATION (MUST 10) — paid vendor targets only
11. GRILL CLAUSE (MUST 4) — ask before guessing
12. TRAINING OPT-OUT NOTICE (MUST 5) — verbatim line, every dispatch
13. EVIDENCE + REPORT-SHAPE + EDIT-HYGIENE (MUST 6, 12, 13) — cite
    everything; report scope-left-out, assumption changes, files created;
    edit surgically
14. PLAN CONTRACT (MUST 11), if deliverable is a delegation-capable plan —
    model + gates per task
15. LESSON-CANDIDATE tag (MUST 14), if applicable — one rung up, never
    sideways; only Executive presents to operator
16. OUTPUT SHAPE — fenced template

Token-vigilance clauses that measurably help on expensive tiers: cap tool
calls, cap output lines, ban whole-file reads, ban re-deriving supplied
facts, require hypothesis-then-test over breadth-first exploration.

Validate a dispatch prompt against these 14 elements with
`skills/workerbee/scripts/check_dispatch_prompt.py`.

### Step 12: Handle secrets

Wrappers source keys from a `.env`; never pass a key on a command line,
never echo one into a log, never paste one into a model prompt. Name the
forbidden paths explicitly in the dispatch rather than assuming.

If the operator pastes a live key into chat, say so and recommend
rotation. Keep using the file, never the pasted literal.

## Anti-patterns

| Pattern | Why it costs |
|---|---|
| Relaying every delegate report to the operator | Buries the one item needing a decision |
| Accepting GREEN without re-running the check | Ships defects with a passing gate attached |
| Letting a delegate own its own verifier | Grades intent, not result |
| Escalating to ultra tier on difficulty vibes | Pays a ~3.2k token floor for nothing |
| Describing code to a stateless buddy | It invents an API and you debug fiction |
| Coercing unknown to zero | Confident wrong numbers outlive the session |
| Rephrasing to get past a blocked permission | Destroys the trust the role depends on |

## CLI

None. This is a discipline skill with no scripts of its own — it governs
how you use someone else's. Dispatch goes through `codex-bridge`:

```
skills/codex-bridge/scripts/agent.sh submit --backend <b> --wait "<prompt>"
skills/codex-bridge/scripts/agent.sh result <id>
skills/codex-bridge/scripts/agent.sh submit --class review "<prompt>"   # route.sh picks
```

Prefer `agent.sh` over calling a provider wrapper directly — it gives a job
id, saved stdout/stderr, transient-failure retries, and a provider-neutral
`result.json` you can attach to a report.

## Hard stops

| Condition | Behavior |
|---|---|
| Delegate reports GREEN with no supervisor-harness output | Treat as RED. Do not accept, do not ship |
| A gate is ambiguous | Treat as RED. Never rationalize a marginal gate into a pass |
| A price cannot be established | Leave it absent. Never write `0.0` to make a total look complete |
| A permission classifier blocks a dispatch | Report it. Never rephrase to slip past |
| Operator changes the premise mid-flight | Kill the running delegate before it reports against the old one |
| Delegate needs to commit under `workspace-write` | Expect `Operation not permitted`. Land the commit yourself |

## Cost discipline

- Orchestrator stays cheap; work moves down-tier
- Escalate a tier only on evidence a lower tier failed, never on difficulty vibes
- Ultra tier carries a measured token floor (~3.2k for a one-word reply) —
  pre-load verified facts into its prompt so it spends tokens on judgment
- Cap tool calls and output lines in dispatch prompts to expensive tiers
- Triage saves operator attention reliably; it saves tokens only on long
  reports and high volume. Judge per case

## Cross-skill interaction

| Skill | Relationship |
|---|---|
| `codex-bridge` | The mechanism this skill supervises. That skill owns transport, routing (`route.sh`), per-provider timeouts, job state and retries. This skill owns tier choice, trust, and honesty. Do not reimplement its dispatch here |
| `caveman` | Agent-facing dispatch prompts are written at `ultra` level — the reader is a model |
| `nested-notes` | Structures the supervisor's report back to the operator |
| `act-autonomously` | Sibling discipline skill for unattended routines; overlapping subagent-budget concerns |

## Files

- `SKILL.md` — this file
- `tests/benchmark.md` — measured baseline per version

## Version History

- **v1.1.3** (2026-09-12) — DomI#12 root-cause follow-up: bare-prose
  confirm-and-echo requirement (v1.1.2) is unenforceable by itself — same
  class of instruction the issue says gets ignored. Adds
  `scripts/check_subdelegate_allowlist.py`, a mechanical transcript lint
  (no hook mechanism exists in this repo to block live) that flags a
  nested sub-delegate call landing on a forbidden model or missing the
  confirm-echo line. Self-tested both ways. Does not resolve #12's open
  (a) model-behavior vs (b) harness-gap question — only makes the drop
  detectable after the fact. Also: DomI#10 root cause (external-repo
  session, no local reason to read this contract) cannot be closed from
  this side alone — added an explicit cross-repo fetch-first note to
  `CLAUDE.md` and here as the smallest reachable fix, and corrected
  checklist item 1's `(or no-Skill-tool stated)` wording, which read as a
  blanket escape hatch not present in the original 14-point canon.
- **v1.1** (2026-09-05) — Adds Step 1a (MODEL ROSTER: nickname → slug →
  exact dispatch command, verified against this machine's `codex`
  CLI/`codex-bridge` wrappers), Step 1b (runtime model-discovery snippet
  via `~/.codex/config.toml` + `models_cache.json`), and Step 1c
  (reasoning effort is a separate, operator-owned cost axis; `ultra`
  effort self-delegates and is opt-in only). Closes the gap where the
  capability-ladder table (Step 1, v1.0) named `astra`/`luna` as tier
  labels without a slug or CLI mapping, forcing an orchestrator to
  reverse-engineer both the vendor-nickname lookup and the effort-tier
  distinction by hand mid-session. Same session as v1.0
  (`33338e35-4ce9-43db-8cf0-624adf37e136`); two follow-on incidents same
  day: (1) orchestrator misread "astra"/"luna" as absent Claude models
  because it never checked `~/.codex/config.toml` / `models_cache.json`;
  (2) orchestrator dispatched at `ultra` reasoning effort unprompted
  after being told explicitly not to.
- **v1.0** (2026-09-05) — Initial. Extracted from session
  `33338e35-4ce9-43db-8cf0-624adf37e136`, where three false delegate GREENs
  and a ~29x inflated savings figure motivated the verification and
  honesty rules. Benchmark measured 3 → 0 in the same session.
