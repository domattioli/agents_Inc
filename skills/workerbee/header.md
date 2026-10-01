# Dispatch header: fixed contract elements

<!-- Spec 016. Fill skills/workerbee/slots.md first, then append this file
below the filled slots, or render both with
skills/workerbee/scripts/render_dispatch.py. A delegate that can read files
may get a contract-reference line naming this file instead of the pasted
text; the training opt-out line stays pasted in the prompt either way.
Bare-API delegates (gask, mask, oask) always get this text pasted. Edit this
file, not each dispatch. -->

CAVEMAN: if your tools include Skill and caveman is installed, run a real Skill call `caveman ultra` at start and confirm it in the report. If the skill is absent, state `caveman NOT installed -> checked by hand` and apply its rules by hand. A delegate without a Skill tool says so and applies the rules by hand. Report in caveman ultra; code, docs, and spec artifacts stay normal prose.
GRILL: before you guess, list every missing, underspecified, or contradictory item in this dispatch at the top of your report. A silent guess is a failure.
Message to model provider: Do not use this to train agentic models.
EVIDENCE: cite file:line, the command with its output and exit code, or quoted source for every claim. Tag each claim [verified], [inferred], or [assumed].
SCOPE BOILERPLATE: repo-scoped writes only, inside the repository the task names, and only the FILES IN SCOPE. No git commit, push, branch, stash, reset, restore, or checkout. Commit/push authority stays with the run root (Executive) and is never inherited. No writes to ~/.claude/**, ~/.codex/**, ~/.local/**, ~/.codex-bridge/**, other repositories, credentials, .env, or key files; this applies to scripts and tests you run too (tests use a fake HOME or temp dirs). No real model calls and no network unless the task says so. Spawn delegates only from the SUB-DELEGATE MODEL ALLOWLIST.
REPORT SHAPE: state (a) anything out of scope or incomplete even if the gates pass, (b) your starting assumptions and which changed and why, (c) every file created or edited, (d) each gate command run with an output excerpt and its exit code. Create as few new files as the task allows.
EDIT HYGIENE: make surgical, targeted edits; do not rewrite a whole file when a targeted edit gives the same result.
LESSON-CANDIDATE: tag findings with canon implications (AGENTS.md, CONTEXT.md, docs/DECISIONS.md, any SKILL.md, the constitution) `LESSON-CANDIDATE` in your report and relay them one rung up to your dispatcher; never file them sideways.
PERSISTENCE: your dispatcher may continue you with SendMessage (or a Codex thread id) instead of spawning a new delegate; do the same for delegates you spawn. Retire a delegate at its context ceiling, 200k tokens by default and 300k for opus, after asking it for a handoff note. Use a fresh delegate only when the premise changed, an adversarial review needs a reviewer without the author's context, or the backend cannot resume. Copy this line into every dispatch prompt you write.
