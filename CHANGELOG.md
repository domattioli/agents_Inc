# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Dispatch slot gaps from #100: a `GATES` entry may be a plain command string (shlex-split, no shell) as well as an `{argv, cwd, timeout_s, expect_rc}` object, and a blank `PRE_EXISTING_CHANGES` is filled by the renderer with the snapshot placeholder text and one `--allow` per path in `FILES_IN_SCOPE`. QUICKREF and `slots.md` show the GATES object shape.
- Sandboxed sessions no longer learn about the #94 refusal at dispatch time: doctor warns `WB_SANDBOX_EXCLUDE_MISSING` when the Claude settings file lacks `"agents-inc *"` under `sandbox.excludedCommands`, and the session-start hook names that exact operator ask. `agents-inc install` and `repair` now add that entry on the Claude host (other entries untouched) and `unwire` removes only it. The hook also explains `INSTALL_STALE`.
- The report lint accepts the contract's no-gate form `exit code N/A`, and the `[verified]` exit check no longer fires on `exit` used as a plain word (#91).
- The snapshot verify gate is one plain command: capture records the repository, `verify` takes `--repo` or reads it from the snapshot, and the renderer refuses a verify gate written with `cd` or `&&` (#92).
- `--resume <run id>` searches every parent directory a dispatch could have used and lists them when it finds no run; the status line names the absolute run directory to resume (#93).
- `agents-inc install` after `pip install --user` or pipx no longer fails with `WB_CONFIG_CONFLICT`: the console script pip writes to `~/.local/bin/agents-inc` is recognised as this package's own launcher, kept in place, and left alone by `uninstall`. Found by the new clean-install container check.

### Added

- A clean-install check in Docker (`docker/Dockerfile.ci`, `docker/ci_check.sh`, workflow `docker-install`): builds the wheel, installs it as an unprivileged user with an empty HOME and no Claude or Codex CLI on Python 3.11 and 3.14, then runs `install`, `doctor`, a dry-run dispatch, a snapshot verify from outside the repository, and `uninstall`. It covers install drift and the Linux half; the macOS sandbox paths stay on the Mac.
- The release workflow deposits each release on Zenodo itself (`tools/zenodo_deposit.py`): a new version of the newest record under concept DOI 10.5281/zenodo.22670100, with the built wheel and sdist and metadata from `.zenodo.json` at the tag. It needs the repository secret `ZENODO_TOKEN`. It is a no-op when the version is already archived and refuses when the version sits under another concept. 0.4.2 needed a hand deposit, and the hand deposit picked up a stale local `dist/`.

### Removed

- Python 3.10 support: the package now requires Python 3.11 or later. The 0.4 releases stay installable on 3.10 (#90).

## [0.4.2] — 2026-10-23

Version 0.4.2 because PyPI has 0.4.1 and the merged work since then is two features and several fixes. Constitution VIII-A makes a 0.x feature a minor bump; the operator chose a patch release anyway (2026-10-22).

### Added

- `agents-inc dispatch` keeps each Claude delegate's usage from `claude -p --output-format json` (per-model tokens, list-price cost, turns) in `usage.json` in the run directory and in `<state>/dispatch-runs/<run-id>/`. `agents-inc ledger append` fills the token columns from it.
- Token bench: `tools/delegation_bench.py` and the size-S build-test-verify fixture (`fixtures/build-test-verify/S/`). Arms A0, A1, B, C and Acheap, one isolated home per arm, hidden acceptance judge. Plan: `docs/proposals/delegation-savings-test.md`.

### Changed

- The agent nudge and session-start text say that the named model is the rung and the route is always `agents-inc dispatch`. `WB_CLI_NOT_FOUND` is explained as "Codex not installed".
- D66 amends D65: the sandboxed-caller fix text names only `"agents-inc *"` in `sandbox.excludedCommands`, run as one plain command. It no longer offers `dangerouslyDisableSandbox`, which auto mode refuses.

### Fixed

- The haiku alias points at `claude-haiku-5-5`.
- `gask.sh`, `mask.sh`, `oask.sh` and `codexagent.sh` write temp files under `TMPDIR` when it is set. macOS `mktemp` with no template ignored it, and the sandbox denied the default path.
- The token bench passes `CLAUDE_CODE_OAUTH_TOKEN` and `ANTHROPIC_API_KEY` through its env scrub, checks `claude auth status` once per arm, writes install failures to `homes/<arm>/install.log`, and resolves `--out` to an absolute path.
- `.zenodo.json` sets `license: polyform-small-business-1.0.0`. With no license id, Zenodo showed 0.4.1 as `cc-by-4.0`, which contradicts LICENSE; the no-AI-training term stays in `notes`.

## [0.4.1] — 2026-10-21

0.4.0 was published and withdrawn on the same day; 0.4.1 replaces it. The only change from 0.4.0 is the software title ("Cross-Vendor Governance for an Agentic-AI Workforce") and the matching PyPI summary.

### Added

- Every Claude delegate prompt carries a GRANTS section: the tools, `BASH_ALLOW` prefixes and denied tools of the run. A harness "requires approval" block is a missing grant, not a policy refusal; delegates run one plain command per Bash call. `BASH_ALLOW` prefixes should bind the issue number and `-R repo` (D58 addendum, #54).
- Codex delegates spawn Workers on the same terms as Claude delegates (D57, #68). `agents-inc dispatch` runs astra, sol or terra as a broker Lead when FAN_OUT total is above 0 and ALLOWLIST names models; the roster follows the D46.3 rung rule. A Codex Lead may now write to cwd; its broker run directory sits outside cwd.
- Agent gate (D61): the agent-nudge hook can block Claude `Agent`/`Task` calls that bypass agents-inc. Default `advisory` blocks nothing; `agents-inc repair --agent-gate enforce` allows only foreground Explore, Plan, claude-code-guide and statusline-setup. `AGENTS_INC_AGENT_GATE` overrides per session. Install lists the hooks it adds, `agents-inc doctor` prints the gate mode, and `agents-inc unwire` removes agents-inc hooks only.
- Claude delegates (fable, opus, sonnet) spawn Workers through the credential-blind broker when FAN_OUT allows it and ALLOWLIST names lower-rung models. The broker checks the parent run's token, roster, fan-out, permission mode and tool grants. Workers cannot lead (D60).
- Dispatch fails loud (spec 022, D64). New red reasons: `blocked`, `timeout`, `rc-nonzero`, `launch-failed`, `snapshot-tampered`, `snapshot-error`. The status line gains `detail=`, `report=none`, `snapshot=none` and `snapshot=TAMPERED`.
- `agents-inc dispatch` exits 69 when blocked and 75 on quota pause. The broker still reports both as red.
- Scope gate verifies against a trusted snapshot copy outside the delegate's cwd (`<state>/dispatch-runs/<run-id>/`, mode 0700).
- Every dispatched turn (Claude and Codex) runs under a deadline: `AGENTS_INC_TURN_TIMEOUT_S`, default 3600, `0` for none.
- Doctor reports `WB_CLAUDE_NOT_FOUND` and warns `WB_SANDBOX_NESTED`; the session-start hook shows warnings.
- `FILES_IN_SCOPE` glob patterns are refused (`refused-scope`).
- Snapshot trust fails closed: a failed trusted copy, a relabelled or mismatched run.json, or a missing private record turns the run red. Cancelled runs kill and reap the delegate's process group.
- The gate and BASH_ALLOW credential screen refuses `.env` files of any name, key files with suffixes, secret basenames, secret env-var names and token flags. `test_token_refresh.py` still passes.
- A Codex 429 or "model is at capacity" exits 75. A stray 429 on a clean turn no longer counts as a quota pause.
- A dispatch started inside the Claude Code Bash sandbox or a Codex sandbox stops before any child starts: red `blocked`, `detail=caller-sandboxed:...` with the fix, exit 69 (D65, #94). `AGENTS_INC_ALLOW_SANDBOXED=1` turns the check off.
- A credential-seeking refusal names the slot and the matched text in `reason_detail`, in dispatch and in the broker result (#95).
- The GRANTS section says that Edit and Write under `--cwd` come from `PERMISSION_MODE acceptEdits`.

### Changed

- Sub-delegation no longer allows Agent-tool Claude models; Leads sub-delegate only via `agents-inc dispatch` (D59). Future examination: Agent-tool scouts can be watched live in Claude Code like native agents, which dispatch runs cannot yet. Revisit once dispatch offers the same live view.
- `agents-inc doctor` prints a note that Codex delegates have no network unless a dispatch opts in (#66).
- `slots.md`: a Codex delegate writes only inside `--cwd`; dispatch with `--cwd <repo>` to edit another repository (#66).
- Release workflow checks that Zenodo archived the release under concept DOI 10.5281/zenodo.22670100.

### Fixed

- `pre_dispatch_snapshot.py verify --allow a b c` accepts several paths after one flag; it exited 2 before. The repeated `--allow` form is unchanged.
- Report lint accepts `WORKERS SPAWNED: <n> this turn (...)` on a resume turn, and flags `verified-exit-without-code` when a `[verified]` line about an exit or gate result carries no exit code.
- A delegate that stops on a usage limit now ends `outcome=red reason=quota-paused` instead of a misleading report reason; a quota pause counts as one failed attempt.
- `agents-inc dispatch --resume` accepts a run-directory path as well as a run id; a path used to fail with `no run.json`.
- `check_dispatch_prompt.py` reads a `FAN_OUT:` line wrapped in a list bullet, backticks or bold marks, or ending in punctuation (#66).
- A broker Claude Worker no longer nests its own Bash sandbox inside the broker's `sandbox-exec` profile, which failed with rc 71. Its profile allows Claude Code's `/tmp/claude-<hex>-cwd` file, so Bash works with the Worker's sandbox off (D65, #94).
- The credential slot screen no longer refuses "200k tokens", "tokenizer" or `~/.claude/skills/` paths. `token` as a word and `~/.claude/skills/../` still match (#95).

## [0.3.1] — 2026-10-10

Codex delegates can opt into network access and now run heredocs and their own snapshot check inside the sandbox. Versioned as a patch by operator ruling, although it adds an opt-in flag (Constitution VIII-A would make it 0.4.0).

### Added

- Update notice: the session-start hook and `agents-inc doctor` say when PyPI has a newer agents-inc, with the update command. At most one request to pypi.org a day, 2 s timeout, silent on failure; opt out with `AGENTS_INC_NO_UPDATE_CHECK=1`.
- `agents-inc report bug|feature`: drafts a GitHub issue for agents_Inc with version, doctor codes, OS and Codex version; home paths redacted, likely secrets refused. Prints only; `--submit` files it through the caller's `gh` login.
- Codex network opt-in (#66, D56): slot `CODEX_NETWORK: yes` or `agents-inc run --network` lets a Codex delegate's tool commands reach the network. Default stays off.

### Changed

- `docs/governance/DELEGATION-MODEL.md` 2.0.0 uses the D46 roles (CEO, CoS, Lead, Worker) in place of Exec and Super; reviewed by sol.

### Fixed

- Codex tool commands get a private writable temp dir (`TMPDIR`, `TMPPREFIX`), so heredocs work; a dispatched Codex delegate gets a copy of `pre_dispatch_snapshot.py` in its run directory (named in the prompt as `SNAPSHOT VERIFIER`) and can run its own FAILURE GATE check (#66). Tool commands use an empty global git config, and the snapshot records ignored paths at capture, so a sandboxed verify matches the supervisor's.
- DelegateAgent MCP server used `gpt-5.6-luna` after the pin moved; it now reads the luna slug from `routing.json`.
- Skill tests and the codex-bridge demo no longer ship in the sdist and wheel.
- `pre_dispatch_snapshot.py verify --allow <file>` no longer reports `CHANGED <dir>/` when the allowed file sits in a new directory (#66).

## [0.3.0] — 2026-10-10

Codex delegates now work like Claude subagents, installs need only pip, and every dispatch carries a reporting chain and a ledger row.

### Added

- Model sync: new Claude and Codex models are detected and promoted, with `approve` or `auto` mode and pins (#57).
- Reporting chain (#45): every dispatch prompt carries a `REPORTING CHAIN` line derived from the ladder. Precedence is explicit slot, then the `agents-inc models chain` setting, then the ladder default. A lint rule rejects an inverted chain.
- Dispatch ledger rows (#49): each launched dispatch writes one `dispatched` ledger node; `ledger append --run-id`.
- Pip-only install (#55, D55): skills and the schema ship as package data, so `agents-inc install` and `repair` work without `--source`.
- Codex delegates match Claude subagents by default: tools on and write access to `--cwd` whenever `PERMISSION_MODE` allows edits. `CODEX_WRITE: no` opts out.
- New wide logo, generated by sol through `agents-inc dispatch`.

### Fixed

- Codex delegates can read their skills and built-in image output, start from a repo subfolder, read their dispatch snapshot, and run perl tools such as `shasum`. All five were blocked by the D49/D51 sandbox.
- The report lint and the dispatch parser accept an evidence tag before the `WORKERS SPAWNED` line (#56).
- Install no longer records a temporary or shim `codex` path (#50); `doctor` warns `WB_CLI_TEMP_PATH`.
- `agents-inc run` with a Claude alias exits 2 and prints the matching `dispatch` command (#46).
- `free_health`: an ok report clears `last_error` (#42).
- `demo/` and `docs/proposals/` are left out of release artifacts.

Please cite: Mattioli, D. O. (2026). *agents_Inc: A Model Ladder for Delegating and Verifying Work Across AI Agents* (Version 0.3.0) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.22670100 (author ORCID: https://orcid.org/0000-0002-7327-6337)

## [0.2.0] — 2026-10-07

### Added

- D47 — `agents-inc dispatch` wraps the dispatch loop.
- D48 — Fan-out cap for delegation.
- D49 — Codex tool access by rung.
- D50 — Codex becomes optional; both-optional deferred to v1.0.
- D51 — Credential-blind dispatch broker.
- D52 — Model pins, drift warnings, operator-decided bumps.
- D53 — QUICKREF loads by hook on first dispatch.
- D54 — delegate turns (`--resume` for Claude and Codex, broker `resume` tool) and a live `ask_lead` channel from a running Worker to its Lead.
- D49.1 — luna accepts `--tools` and `--write` like the other Codex aliases.
- Spec 018 wave 1 — MCP protocol hygiene for the broker and Worker servers: version negotiation (2025-06-18, 2024-11-05), `outputSchema` and `structuredContent` on broker tools, an explicit MCP timeout for Claude Workers, broker request ids that survive a restart, and redaction of encoded secret values.
- LICENSE: PolyForm Small Business License 1.0.0 plus a licensor-added term that forbids AI/ML training use.
- First PyPI package, `agents-inc` (import name `agents_inc`), built and published by a tag-triggered release workflow.
- Citation metadata for 0.2.0 in `CITATION.cff` and `.zenodo.json`.

## [0.1.0] — 2026-10-01

First tagged release. The project is experimental: the governed path
(`WORKERBEES_GOVERNANCE`) is off by default.

### Added

- Governed routing across Claude, Codex, Gemini, Mistral, OpenRouter, and an
  opt-in local ollama pilot, with deterministic verification, cross-vendor
  review, and an append-only ledger.
- `agents-inc` installer and launcher: install, repair, doctor, rollback, and
  uninstall, with receipt-owned and reversible changes to host configuration.
- Host wiring: a managed instruction block and session hooks in each detected
  host (Claude Code, Codex, Gemini).
- `@alias` side questions from inside a session (`at_route` hook), including
  `@openrouter`. The installer now owns the hook and the alias links (#41, #38).
- Host ledger: delegated calls made from the host session (Agent, Task, and
  DelegateAgent) leave a dispatch row, and `agents-inc ledger append` and
  `agents-inc ledger pending` record verified returns (#36).
- Ledger fields for effort, tokens, cache use, and files created, plus a
  time-window join against usage data (#36).
- Workerbee skill: rung names, a generated tier table with a drift check, a
  rule to keep a delegate until its context ceiling (#28), and a fixed dispatch
  header with fill-in slots and a renderer (#36, #4).
- Persona guard: an Agent or Task description that starts with a Codex persona
  name (astra, sol, terra, luna) is denied, and duplicate spawns of the same
  task from another session raise a warning (#17, #13).
- Transcript recovery helper for interrupted delegates (#13).

### Fixed

- Provider health reports how fresh each result is, and the OpenRouter key is
  found under either name, preferring `OPENROUTER_API_KEY` (#22).
- The launcher runs from any directory and reports a missing install (#35).
