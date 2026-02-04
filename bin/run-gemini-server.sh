#!/bin/bash
# Gemini MCP Server launcher
# Run with: mcporter (stdio) or directly for testing

cd "$(dirname "$0")/.."
source .venv/bin/activate

export GEMINI_TASK_DIR="${HOME}/.agent/gemini/tasks"
export GEMINI_CLI="gemini"
# Load DID from identity file if it exists
if [ -f "${HOME}/.agent/gemini/archon/did.txt" ]; then
    export GEMINI_AGENT_DID="$(cat ${HOME}/.agent/gemini/archon/did.txt)"
else
    export GEMINI_AGENT_DID="${GEMINI_AGENT_DID:-did:cid:gemini}"
fi

exec python -m servers.gemini_server
