#!/bin/bash
# Hex MCP Server launcher (callbacks/coordination)
# Run with: mcporter (stdio) or directly for testing

cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true

export HEX_TASK_DIR="${HOME}/.agent/hex/tasks"
export HEX_AGENT_DID="did:cid:bagaaieratn3qejd6mr4y2bk3nliriafoyeftt74tkl7il6bbvakfdupahkla"

exec python3 -m servers.hex_server
