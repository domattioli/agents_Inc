#!/usr/bin/env bash
set -euo pipefail

# Governed asynchronous dispatcher for the existing Codex, Gemini, and Mistral legs.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/agent_runner.py" "$@"
