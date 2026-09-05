---
name: codespace-exec
description: Run project inspection, build, test, and lint commands in the operator's existing GitHub Codespace instead of on the local Mac. Use for remote project command execution and Codespace execution status.
version: 1.0.0
benchmark: mac_minutes_spent_on_work_that_belonged_in_the_codespace
---

# Codespace Exec

This skill sends project commands to the existing GitHub Codespace `super-duper-fortnight-6r44v6jwxjrhr5x5`. Use it for repository inspection, builds, tests, and linters that should consume Codespace compute rather than local Mac resources.

Run commands through the scripts in this skill. Never silently fall back to executing a requested command locally. A remote failure, unavailable Codespace, or authentication problem must remain a visible failure.

## Hard prohibitions

- Never create, rebuild, or delete a Codespace. If the named Codespace is missing or unavailable, report the problem and stop. Do not create a replacement.
- Never stop the Codespace unless the operator explicitly asks. Do not add automatic stop-on-exit or idle-shutdown behavior.
- Never reset, force-checkout, stash, clean, or otherwise discard repository changes. This integration executes commands; it does not manage branches or working-tree state.

## Authentication preflight

Every operation first checks GitHub CLI availability, authentication, the `codespace` OAuth scope, and the named Codespace. Run the preflight directly with:

```bash
skills/codespace-exec/scripts/preflight.sh
```

If GitHub reports HTTP 403 or says the `codespace` scope is missing, the operator must run this interactive command:

```bash
gh auth refresh -h github.com -s codespace
```

Do not attempt to bypass a missing scope.

## Execute a project command

Place the command and its arguments after `--`:

```bash
skills/codespace-exec/scripts/exec.sh -- npm test
skills/codespace-exec/scripts/exec.sh -- rg -n "TODO item" src
skills/codespace-exec/scripts/exec.sh --dir /workspaces/project -- make lint
```

The first successful execution resolves the repository directory under `/workspaces` and caches it in `~/.codespace-exec/state`. If several directories are present, rerun with `--dir PATH`. Invalidate the cached path when the Codespace workspace layout changes:

```bash
skills/codespace-exec/scripts/exec.sh --invalidate-cache -- npm test
```

The command's output streams directly and its remote exit status is returned unchanged.

## Timeouts and exit status

| Operation | Environment variable | Default |
|---|---|---:|
| Codespace shell connection/startup | `CODESPACE_CONNECT_TIMEOUT` | 120 seconds |
| Remote command execution | `CODESPACE_EXEC_TIMEOUT` | 600 seconds |

The 10-minute execution budget gives substantial headroom over the operator's roughly 45-second test suite. A connection or execution timeout exits 124; ordinary remote command failures retain their remote status, while authentication preflight's missing-scope error remains 12. The scripts use `timeout` or `gtimeout` when installed and otherwise enforce the same limits with a shell watchdog.

## Report status

```bash
skills/codespace-exec/scripts/status.sh
skills/codespace-exec/scripts/status.sh --dir /workspaces/project
skills/codespace-exec/scripts/status.sh --invalidate-cache
```

Status reports the fixed Codespace name and state, scope-preflight result, resolved repository path, remote hostname, current branch, and whether the remote working tree is clean. It is read-only.
