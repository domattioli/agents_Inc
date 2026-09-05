# Codex Bridge

HTTP server bridging local `codex` CLI to remote clients via authenticated POST requests.

The repository also includes a local multi-provider job runner at
`skills/codex-bridge/scripts/agent.sh`. It dispatches existing Codex, Gemini,
and Mistral wrappers as inspectable jobs with task IDs, status, saved output,
transient retries, and persistent follow-ups for Codex or Mistral-agent work.
Use `CODEX_BRIDGE_MODE=ultra` to enforce no-Anthropic routing.

## Docs

| file | reader |
|---|---|
| [`docs/START-HERE.md`](docs/START-HERE.md) | new human, plain language |
| [`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md) | operator/agent, caveman ultra |
| [`docs/EXTENDING.md`](docs/EXTENDING.md) | adding a vendor, model, task class, or domain |
| [`skills/workerbee/SKILL.md`](skills/workerbee/SKILL.md) | full supervision discipline |

Two halves, deliberately separate: `skills/codex-bridge/` is mechanism (transport, routing, retries, cost logging), `skills/workerbee/` is judgment (tier choice, trust, verification). No code in the second, no opinions in the first.

## Requirements

- Python 3.9+
- `codex` CLI installed and logged in on PATH

## Run

```bash
export CODEX_BRIDGE_TOKEN=$(openssl rand -hex 32)
python3 bridge.py --port 8787
```

Use `--workdir DIR` to set the working directory for codex execution (default: current working directory). The `--workdir` does not need to be a git repository — the bridge always passes `--skip-git-repo-check` to codex.

## API

### Persistent Sessions

The bridge maintains one codex thread across requests. Context carries over between prompts, enabling multi-turn conversations. Each prompt reuses the current thread (tracked by `thread_id`); set `"reset": true` in the request to start a new session.

### GET /health

No authentication required.

```bash
curl http://127.0.0.1:8787/health
```

Response:
```json
{"status":"ok"}
```

### GET /session

Returns the current session thread ID.

```bash
curl -H "X-Auth-Token: $CODEX_BRIDGE_TOKEN" http://127.0.0.1:8787/session
```

Response:
```json
{"thread_id":"01a0645e-..."}
```

When `thread_id` is `null`, the next prompt will start a fresh session.

### POST /reset

Clears the current session and starts fresh on the next prompt.

```bash
curl -X POST -H "X-Auth-Token: $CODEX_BRIDGE_TOKEN" http://127.0.0.1:8787/reset
```

Response:
```json
{"reset":true}
```

### POST /prompt

Executes a prompt via `codex exec`. Reuses the current thread by default; set `"reset": true` to start fresh.

```bash
curl -X POST http://127.0.0.1:8787/prompt \
  -H "X-Auth-Token: $CODEX_BRIDGE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"explain currying in Haskell","model":"gpt-5-codex"}'
```

Request body:
```json
{
  "prompt": "string (required)",
  "model": "string (optional; overrides --model flag)",
  "reset": "boolean (optional; start fresh session if true; default: false)"
}
```

Response (success):
```json
{
  "response": "<codex output>",
  "thread_id": "01a0645e-...",
  "usage": {"input_tokens": 1234, "output_tokens": 567}
}
```

Response (error):
```json
{"error":"error message","stderr":"<stderr tail if applicable>"}
```

The `usage` field is populated when available (after first turn in a session). `thread_id` identifies the active codex session; it updates on the first prompt and persists until `reset` or `/reset` is called.

## Exposing via Tunnel

### ngrok

```bash
ngrok http 8787
```

Free-tier URLs rotate every 2 hours. Use ngrok's paid plan for a reserved domain:

```bash
ngrok http 8787 --url=<your-reserved-url>
```

### Cloudflared

Install Cloudflare Tunnel:
```bash
brew install cloudflared  # macOS
# Or download from https://github.com/cloudflare/cloudflared/releases
```

Quick tunnel (one-off, auto-domain):
```bash
cloudflared tunnel --url http://localhost:8787
```

Named tunnel (persistent):
```bash
cloudflared tunnel login
cloudflared tunnel create codex-bridge
cloudflared tunnel route dns codex-bridge codex.example.com
cloudflared tunnel run --url http://localhost:8787 codex-bridge
```

### Tailscale Funnel

Requires Tailscale installed and logged in. Funnel exposes to public internet.

```bash
tailscale funnel 8787
```

Safer alternative (tailnet-only, no internet exposure):
```bash
tailscale serve 8787
```

Tailnet users access via `https://<machine-name>.<tailnet-name>.ts.net`.

## Security

- **Token is the only gate.** Use a long random token (e.g., `openssl rand -hex 32`), rotate regularly.
- **Prefer tailscale serve** over public funnel; tailnet is isolated from internet.
- **Bind to 127.0.0.1 only** (default); avoid `--host 0.0.0.0`.
- **Codex runs with your local permissions.** Token grants shell access; protect it like a private key.
- Keep tokens out of shell history: `export CODEX_BRIDGE_TOKEN=$(openssl rand -hex 32)` or load from a secure env file.

## Error Responses

| Status | Meaning |
|--------|---------|
| 200 | Success; operation completed. `/prompt` returns response + thread_id + usage; `/reset` returns `{"reset":true}`; `/session` returns `{"thread_id":…}`. |
| 401 | Unauthorized; `X-Auth-Token` missing or incorrect. |
| 400 | Bad request; invalid JSON, missing `prompt` field, non-string `prompt`, non-boolean `reset`, or `Content-Length` unparseable. |
| 413 | Payload too large; request body exceeds 1 MiB. |
| 500 | Internal server error; codex CLI not found on PATH, or unhandled exception. |
| 502 | Bad gateway; codex exited with non-zero status. Response includes stderr tail. Stale-session recovery: if `/prompt` used `resume` and failed, the bridge retries as fresh (one retry). |
| 504 | Gateway timeout; codex execution exceeded `--timeout`. |
