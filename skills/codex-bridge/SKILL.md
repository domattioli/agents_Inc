---
name: codex-bridge
description: Start/stop/query the local Codex HTTP bridge and send prompts to a persistent OpenAI Codex session. Use to offload bulk file digestion, log triage, and second-opinion debugging to GPT instead of spending Claude context. Triggers — "start the codex bridge", "ask codex", "codex bridge status".
version: 1.0.0
benchmark: claude_tokens_saved_per_offloaded_task
---

# Codex Bridge

The Codex Bridge is a local HTTP server that exposes OpenAI's Codex model (GPT-4 or GPT-3.5) as a persistent session with memory. Use it to preserve context across multiple prompts without burning your Claude token budget on bulk file reading, log triage, or debugging second opinions.

## When to Use

**Good use cases:**
- Bulk digestion of large logs, error dumps, or transcripts that don't need to stay in your Claude context window.
- "Second opinion" debugging: ask Codex why a test failed while keeping your Claude session focused on implementation.
- Triage and filtering: ask Codex to scan a dataset and return only the subset you care about, then summarize the results for Claude.
- Exploratory analysis before asking Claude: use Codex to understand the shape of a problem (sample output, error patterns) and feed a summary back to Claude.

**Bad use cases:**
- Anything that needs continuity with this conversation's context—Codex has no access to your Claude session history.
- Work that depends on private code or secrets; the bridge requires a ChatGPT subscription and runs on your machine, but the prompts are sent to OpenAI.
- Tasks better handled by Claude's reasoning: Codex excels at pattern matching and code generation, not at complex reasoning or design decisions.

## Scripts

### up.sh

Start the Codex Bridge server. Idempotent—safe to call repeatedly even if the bridge is already running.

```bash
codex-bridge up [--port N] [--timeout N] [--workdir DIR] [--model M] [--tunnel] [--force]
```

**Options:**
- `--port N`: Listen on port N (default: 8787).
- `--timeout N`: Prompt timeout in seconds (default: 300).
- `--workdir DIR`: Working directory for bridge operations (default: $HOME).
- `--model M`: Force a specific model (optional; defaults to bridge.py config).
- `--tunnel`: Start a Cloudflare tunnel to expose the bridge publicly. Gracefully degrades if `cloudflared` is not installed.
- `--force`: Replace shared bridge state even when it points to a live bridge on another port. Without this explicit override, `up.sh` refuses to strand the recorded bridge.

**Output:** Prints the local URL, tunnel URL (if enabled), PID, workdir, and token file location. Does NOT print the token itself.

**Example:**
```bash
/codex-bridge up --timeout 600 --tunnel
```

### down.sh

Stop the Codex Bridge server and any active tunnel.

```bash
codex-bridge down
```

**Output:** Prints what was stopped (PIDs, URLs). Exit code 0 even if nothing is running.

**Example:**
```bash
/codex-bridge down
```

### ask.sh

Send a prompt to the persistent Codex session and get a response.

```bash
codex-bridge ask [--model M] [--reset] [--raw] "prompt text"
```

Or pass the prompt on stdin:
```bash
cat logfile.txt | codex-bridge ask "summarize this log"
```

**Options:**
- `--model M`: Override the model for this prompt (optional).
- `--reset`: Clear the session history before this prompt (starts fresh).
- `--raw`: Print the full JSON response instead of just the response text.

**Output (default):** The response text, followed by a summary line on stderr: `[thread <id> | in <n> out <n>]` (token counts).

**Output (--raw):** Full JSON response: `{"response": "...", "thread_id": "...", "usage": {...}}`.

**Example:**
```bash
/codex-bridge ask "what error does this code produce?" < error.log

/codex-bridge ask --reset "start fresh: analyze this dataset" < data.csv

/codex-bridge ask --raw "debug this" | jq .usage
```

### status.sh

Check if the Codex Bridge is healthy and print its state.

```bash
codex-bridge status
```

**Output:** Running status (yes/no), local URL, tunnel URL, current thread ID, workdir, uptime.

**Exit code:** 0 if healthy, 1 if not running or unhealthy.

**Example:**
```bash
/codex-bridge status
```

### mask.sh

Send a prompt through a plain Mistral completion or through the configured persistent Mistral agent:

```bash
skills/codex-bridge/scripts/mask.sh --tier code "review this function"
skills/codex-bridge/scripts/mask.sh --agent "research the current alternatives"
skills/codex-bridge/scripts/mask.sh --agent --reset "start a fresh research thread"
```

The agent leg reads its ID from `~/.config/devstral/agent_id` or `MISTRAL_AGENT_ID`, stores the latest conversation ID in `~/.codex-bridge/mistral-conversation-id`, and continues that conversation until `--reset` is used. It is intended for research-style questions where its web-search and code-interpreter tools earn the roughly 26-second latency, not for quick transforms.

### agent.sh

`agent.sh` is the governed local job runner over `ask.sh`, `gask.sh`, and `mask.sh`. It gives each call a task ID, records lifecycle and output locally, supports concurrent submitted jobs, and sends health outcomes to `route.sh`.

```bash
# Auto-select from the current routing mode; return a job ID immediately.
CODEX_BRIDGE_MODE=ultra skills/codex-bridge/scripts/agent.sh submit --class review "review the parser"

# Synchronous job; status is printed when it reaches a terminal state.
skills/codex-bridge/scripts/agent.sh submit --backend gemini --wait "summarize these errors"

# A persistent Mistral agent can be continued later.
id=$(skills/codex-bridge/scripts/agent.sh submit --backend mistral --agent "research X")
skills/codex-bridge/scripts/agent.sh follow-up "$id" --wait "compare the top two"
skills/codex-bridge/scripts/agent.sh result "$id"
```

Commands are `submit`, `status ID`, `wait ID`, `result ID [--stderr|--json]`, `follow-up ID`, and `list`. `--retries 1` through `3` retry only failures that `route.sh` classifies as transient. Job state is private local metadata under `~/.codex-bridge/agents`; set `CODEX_BRIDGE_AGENT_STATE_DIR` for an isolated state directory in automation. Every terminal job also writes `result.json` with a stable provider-neutral schema and paths to its saved stdout/stderr. A future supervisor-side translator can consume that artifact; the runner never invokes one itself.

In `CODEX_BRIDGE_MODE=ultra`, the runner refuses Anthropic names and follows `route.sh` without provider fallback. Gemini is stateless, so only Codex and Mistral jobs created with `--agent` support `follow-up`.

## Delegation timeouts

| Operation | Environment variable | Default |
|---|---|---:|
| Gemini connection | `GASK_CONNECT_TIMEOUT` | 10 seconds |
| Gemini complete request | `GASK_TIMEOUT` | 900 seconds |
| Mistral plain completion | `MASK_TIMEOUT` | 180 seconds |
| Mistral agent request | `MASK_AGENT_TIMEOUT` | 900 seconds |
| Local bridge health/session probe | not configurable | 2 seconds |

The 15-minute generation budgets leave room for deep Gemini output and Mistral agent tool use; the separate 10-second Gemini connection budget fails quickly when the host cannot be reached.

## In-band data-protection declaration

The Gemini leg currently appends the shared opt-out and data-protection declaration from `scripts/data_policy.py` to the end of each non-empty composed request, after any supplied file contents. Injection is enabled by default and is idempotent, so retries or already-prepared prompts receive exactly one copy. Other delegation legs do not currently apply it.

Disable injection for a call by setting:

```bash
CODEX_BRIDGE_OPTOUT=0 skills/codex-bridge/scripts/gask.sh "prompt"
```

This is a declaration sent in-band. Provider data handling is ultimately governed by account settings and terms rather than by prompt text.

## How It Works

The bridge maintains a **persistent OpenAI conversation thread**. Each call to `ask.sh` appends a user message and gets a response while keeping the thread alive. This lets you build context without repeating history.

- Thread ID is stored in `~/.codex-bridge/state.json` and returned after each prompt.
- Token file (`~/.codex-bridge/token`) grants authentication; keep it private (mode 600).
- Logs are written to `~/.codex-bridge/bridge.log` and `~/.codex-bridge/tunnel.log`.

### When to Reset

Use `ask.sh --reset` to start a fresh thread if:
- The session gets confused or diverges from your intent.
- You want to switch tasks completely without history bleeding over.
- Usage tracking shows the thread has grown very large (OpenAI may charge for token usage in the thread history).

## Codex Limits

The bridge uses your ChatGPT subscription, so rate limits and API restrictions apply. You are **not paying per request**; you are subject to OpenAI's **rate limit windows** (typically requests-per-minute). Check your OpenAI account dashboard for current limits.

## Security Note

The token file at `~/.codex-bridge/token` grants shell-level access to codex-bridge operations. Protect it as you would an SSH key or API token. Do not commit it to version control.
