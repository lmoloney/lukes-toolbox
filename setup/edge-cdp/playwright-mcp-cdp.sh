#!/usr/bin/env bash
# Wrapper for @playwright/mcp that auto-detects the Windows host IP from WSL
# and connects to an existing Edge CDP session.
#
# Usage (direct):  ./playwright-mcp-cdp.sh
# Usage (MCP config): set as "command" in mcp.json
#
# Env overrides:
#   EDGE_CDP_PORT  - default 9222
#   EDGE_CDP_HOST  - default: auto-detect Windows host from WSL

set -euo pipefail

PORT="${EDGE_CDP_PORT:-9222}"

if [[ -n "${EDGE_CDP_HOST:-}" ]]; then
    HOST="$EDGE_CDP_HOST"
elif grep -qi microsoft /proc/version 2>/dev/null; then
    # Running in WSL — resolve Windows host IP
    HOST=$(ip route show default | awk '{print $3}')
else
    # Not WSL (native Linux, Mac, etc.) — assume localhost
    HOST="localhost"
fi

ENDPOINT="http://${HOST}:${PORT}"

exec npx -y @playwright/mcp@latest --cdp-endpoint "$ENDPOINT"
