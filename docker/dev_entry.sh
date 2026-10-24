#!/usr/bin/env bash
# Entry for docker/Dockerfile.dev. Copies mounted secrets into the throwaway home, installs agents-inc
# from the checkout at /src, prints doctor, then runs the command (default: bash). Never prints a secret.
set -euo pipefail

if [ -f /run/secrets/codex_auth.json ]; then
  mkdir -p "$HOME/.codex" && cp /run/secrets/codex_auth.json "$HOME/.codex/auth.json" && chmod 600 "$HOME/.codex/auth.json"
  echo "codex: auth copied"
else
  echo "codex: no auth mounted (/run/secrets/codex_auth.json)"
fi

if [ -f /run/secrets/claude.env ]; then
  # Read one key; never source the file (a stray character would run as shell).
  token=$(sed -n 's/^[[:space:]]*\(export[[:space:]]\+\)\?CLAUDE_CODE_OAUTH_TOKEN=//p' /run/secrets/claude.env | head -1 | tr -d '\r"'"'")
  if [ -n "$token" ]; then
    export CLAUDE_CODE_OAUTH_TOKEN="$token"; echo "claude: CLAUDE_CODE_OAUTH_TOKEN set (${#token} chars)"
    # `docker exec` shells do not inherit this process's exports: persist for interactive and `bash -lc` use.
    umask 077; printf 'export CLAUDE_CODE_OAUTH_TOKEN=%s\n' "$token" > "$HOME/.agents-inc-env"
    grep -q agents-inc-env "$HOME/.bashrc" 2>/dev/null || echo '. "$HOME/.agents-inc-env"' >> "$HOME/.bashrc"
  else
    echo "claude: claude.env mounted but no CLAUDE_CODE_OAUTH_TOKEN=<value> line found"
  fi
  unset token
else
  echo "claude: no token mounted (/run/secrets/claude.env)"
fi

[ -d /src/agents_inc ] || { echo "mount the checkout at /src (-v \"\$PWD:/src:ro\")" >&2; exit 2; }
PYTHONPATH=/src python3 -m agents_inc.install.cli install --source /src --no-host-wiring
echo "doctor: $(agents-inc doctor | head -1)"
exec "$@"
