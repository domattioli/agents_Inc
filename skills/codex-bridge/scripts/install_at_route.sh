#!/usr/bin/env bash
set -euo pipefail

# Compute checkout root: three dirs up from script dir
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKOUT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Stub: install_at_route.sh is retired
echo "install_at_route.sh is retired: run agents-inc repair --source $CHECKOUT_ROOT" >&2
echo "agents-inc install now owns the UserPromptSubmit hook and the @alias links" >&2
exit 2
