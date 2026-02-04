#!/bin/bash
# Codex MCP Server launcher
# Run with: mcporter (stdio) or directly for testing

cd "$(dirname "$0")/.."
source .venv/bin/activate

export CODEX_TASK_DIR="${HOME}/.agent/codex/tasks"
export CODEX_CLI="codex"
# Load DID from identity file if it exists
if [ -f "${HOME}/.agent/codex/archon/did.txt" ]; then
    export CODEX_AGENT_DID="$(cat ${HOME}/.agent/codex/archon/did.txt)"
else
    export CODEX_AGENT_DID="${CODEX_AGENT_DID:-did:cid:codex}"
fi

exec python -m servers.codex_server
