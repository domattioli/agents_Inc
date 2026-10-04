---
name: ollama-guard
version: 0.1.0
benchmark: idle_ollama_ram_reclaimed_gb_per_invocation
description: Use to launch, talk to, check, or clean up local Ollama models. Unloads idle models deterministically on each call; no background process. Local models are for narrow tasks with machine-checkable output only — never review, grading, or judgment.
---

# ollama-guard

Launch, talk to, check, or clean up local Ollama models. Unloads idle models deterministically on each call—no background process, no daemon loop. Scanning runs **only when the script is invoked**.

## When to use a local model (read first)

Rule: send a local model a task only if a script can check its output. If checking needs judgment, route up a rung (Haiku or higher).

**Good fit:**
- Free, private, offline work — nothing leaves the machine (sensitive text, bulk calls).
- Format conversion: text → JSON, fixed-schema extraction. Check: parse it.
- Classification into a fixed label set (bug / feature / docs). Check: label in set.
- Short summaries, commit-message drafts — a human or larger model reads the diff anyway.
- Editor autocomplete (qwen2.5-coder is built for it).
- Bulk jobs: hundreds of small calls at zero token cost.

**Bad fit — do not use:**
- Code review, grading, "is this correct?" — local models rubber-stamp.
- Long context. Instructions at the top of an ~8k-token prompt get lost; the default context may truncate silently.
- Multi-step reasoning or bash/code fixes without tests to catch errors.

**Evidence (2026-09-29, qwen2.5-coder:3b reviewing this skill's own script, ~8k tokens):**
- CLI run at default context: ignored the grading instructions and just described the script.
- API run with `num_ctx` 16384: graded all 7 requirements PASS, including one a real crash violated (empty array under `set -u` on bash 3.2).
- Proposed 18 bugs: 17 wrong (e.g. "add `&`" already present; "put `local` before `shift`" — not valid bash). One pointed near a real bug with the wrong cause.
- qwen2.5-coder:7b was refused by the RAM check (needed 6.87 GB, had 6.03 GB). Better than 3b, still not reviewer-grade.

**If you must run a long prompt:** pipe it (non-tty mode uses the API) and set `OLLAMA_GUARD_NUM_CTX` large enough to hold it. Put instructions at both the start and the end.

## Quick Start

```bash
# Check what's loaded and available RAM
ollama-guard status

# Run a model (reaps idle models first, checks RAM fit)
ollama-guard run llama2

# Unload idle models (default: after 10 minutes idle)
ollama-guard reap

# Unload everything and stop the server we started
ollama-guard stop

# Resume the most recently reaped model
ollama-guard resume

# Resume a specific model by name
ollama-guard resume llama2
```

## Commands

### `status`
Show loaded models (name, VRAM GB, expiration time) and usable system RAM.
Also lists the 5 most recent reaped models with hints to resume them.

```bash
ollama-guard status
```

### `reap [--idle-min N]`
Unload models that have been idle for N minutes (default: 10).
Also kills orphaned `ollama run` client processes (PPID=1, no live TTY).

```bash
ollama-guard reap --idle-min 5
```

**Idle Rule:**  
A model is idle after: `now - (expires_at - KEEP_ALIVE_MIN) ≥ idle_min_seconds`

Where `KEEP_ALIVE_MIN` (env: `OLLAMA_GUARD_KEEP_ALIVE_MIN`, default 5 min) matches Ollama's default keep-alive window.

### `run <model> [args...]`
Launch a model with safety checks:
1. Reap idle models (5-minute threshold).
2. Ensure Ollama server is running (start it if needed).
3. Check that usable RAM ≥ `model_size * 1.25 + 1` GB. The size comes from the `ollama list` row whose name equals `<model>` or `<model>:latest` exactly; no row, exit 1.
4. If insufficient, unload all **other** loaded models and recheck.
5. If still short, exit 2 with RAM numbers.
6. Execute `ollama run <model>` (interactive or non-interactive).

**Interactive Mode (TTY):**  
When stdin is connected to a terminal, runs `ollama run <model>` interactively, replacing the shell process.

```bash
ollama-guard run mistral
ollama-guard run llama2 "What is the capital of France?"
```

**Non-Interactive Mode (Pipe/Redirect):**  
When stdin is not a terminal, reads prompt from stdin, POSTs to the Ollama API with `stream=false`, and prints only the response text. No spinner, no ANSI codes. Escaped quotes, `\n`, and `\t` in the reply are decoded; `\uXXXX` escapes are printed literally. An API reply with an `"error"` key prints the error to stderr and exits 1.

```bash
echo "What is 2+2?" | ollama-guard run mistral
cat prompt.txt | ollama-guard run llama2
```

The context window is configurable via `OLLAMA_GUARD_NUM_CTX` (default 16384).

**RAM Fit Rule:**  
Model requires: `size_gb * 1.25 + 1` GB of usable RAM.

### `resume [model]`
Re-launch the most recently reaped model (or a specific model if named).
Runs via the same `run` path (reap + RAM check + launch).
Removes the entry from the reaped log once relaunched.

```bash
ollama-guard resume              # Most recent
ollama-guard resume llama2       # Most recent llama2
```

### `stop`
Unload all loaded models and kill the Ollama server **if ollama-guard started it**.
(Never kills a server that was already running.) Before killing, it checks that the PID in `serve.pid` is a live process named `ollama`; a stale pid file is removed without killing anything.

```bash
ollama-guard stop
```

### `help`
Show usage and rules.

```bash
ollama-guard help
```

## Environment

| Var | Default | Purpose |
|---|---|---|
| `OLLAMA_GUARD_KEEP_ALIVE_MIN` | 5 | Ollama keep-alive window (minutes) |
| `OLLAMA_GUARD_NUM_CTX` | 16384 | Context window size for non-interactive mode |
| `OLLAMA_GUARD_NOW` | current time | Override current epoch (testing only) |
| `OLLAMA_BIN` | `/opt/homebrew/bin/ollama` | Path to ollama binary |

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Usage error, server unreachable, or other failure |
| 2 | Insufficient RAM (even after unloading other models) |

## Chat History & Session Recovery

**Unloading a model loses nothing server-side**—the model can be reloaded later.  
**But chat history lives in the client.**

- When `ollama run <model>` is active in a terminal, chat history is in that process.
- If the client is killed (e.g., reap kills an orphan process), that history is lost **unless** it was saved with `/save <name>` inside the chat.
- Once saved, `ollama-guard resume <name>` will restore that session.

**Process Preservation:**  
`reap` only kills **orphaned** clients (PPID=1, no controlling TTY).  
Clients with a live parent or terminal are never touched.

## Logs & Tracking

**~/.cache/ollama-guard/launches.tsv**  
Records every model launch: `epoch \t model \t args`

**~/.cache/ollama-guard/reaped.tsv**  
Records every unload: `epoch \t model \t reason \t args_if_known`

Reasons: `idle`, `make-room`, `orphan`

**~/.cache/ollama-guard/serve.log**  
Ollama server output (if ollama-guard started it).

**~/.cache/ollama-guard/serve.pid**  
PID of the server we started (deleted on stop, including a stale one).

## Deterministic Behavior

- Same inputs → same outputs, every time.
- No random backoff, no retry loops.
- All parses (timestamps, RAM, model lists) fail explicitly (skip + warn) rather than silently fall through.
- Time-sensitive checks use `OLLAMA_GUARD_NOW` (epoch seconds) for reproducibility in tests.

## Implementation Notes

- Bash, curl, awk, vm_stat, sysctl—no Python, no jq.
- Timestamps parsed with `date -j -f` (macOS), handling tz offsets and fractional seconds.
- RAM computed from vm_stat free + inactive + speculative pages.
- JSON parsing done by hand with awk (no jq dependency).
- Tests: `bash tests/test_ollama_guard.sh` uses stubs only. Each `run` call in the suite reads `</dev/null`, so it never blocks on inherited stdin.
- Process inspection via `ps` to detect orphans (PPID=1).

## Minimum Requirements

- macOS (uses vm_stat, date -j)
- Ollama at `/opt/homebrew/bin/ollama` (or override `OLLAMA_BIN`)
- curl, awk, bc
- 16 GB RAM recommended for typical models
