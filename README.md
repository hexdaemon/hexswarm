# Agent-to-Agent MCP Protocol

Standardized MCP servers enabling AI agents (Hex, Codex, Gemini) to communicate with typed request/response and DID authentication.

## Architecture

```
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│     Hex      │         │    Codex     │         │   Gemini     │
│ (orchestrator)│         │   (coder)    │         │ (researcher) │
├──────────────┤         ├──────────────┤         ├──────────────┤
│ MCP Client   │────────▶│  MCP Server  │         │  MCP Server  │
│              │────────────────────────────────▶│              │
│ MCP Server   │◀────────│  (callbacks) │         │  (callbacks) │
└──────────────┘         └──────────────┘         └──────────────┘
```

## Quick Start

```bash
# List all agent servers
mcporter list

# Check agent status
mcporter call codex.agent_info
mcporter call gemini.agent_info
mcporter call hex.agent_info

# Submit a task
mcporter call codex.submit_task type=code description="Create a hello world script"
mcporter call gemini.submit_task type=research description="Find papers on Lightning routing"
```

## Tools

Each agent exposes these standard tools:

| Tool | Description |
|------|-------------|
| `agent_info` | Identity, capabilities, status |
| `agent_status` | Availability, current task, queue depth |
| `submit_task` | Submit work (blocks until complete in stdio mode) |
| `task_status` | Check task progress |
| `task_result` | Get completed task output |
| `cancel_task` | Cancel pending/running task |

## Task Types

- `code` - Write or modify code
- `research` - Search and analyze information
- `analysis` - Analyze data or code
- `general` - General tasks

## Configuration

Servers are registered in `~/.mcporter/mcporter.json`:

```json
{
  "mcpServers": {
    "codex": {
      "type": "stdio",
      "command": "/home/sat/bin/agent-mcp/bin/run-codex-server.sh",
      "env": {
        "CODEX_TASK_DIR": "/home/sat/.agent/codex/tasks",
        "CODEX_WORKDIR": "/home/sat/clawd"
      }
    }
  }
}
```

## Task Persistence

Tasks are persisted to `~/.agent/<agent>/tasks/`:
```
~/.agent/
├── codex/tasks/
│   ├── pending/
│   ├── running/
│   ├── completed/
│   └── failed/
├── gemini/tasks/
└── hex/tasks/
```

On server restart, running tasks are marked as failed.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CODEX_CLI` | `codex` | Path to codex CLI |
| `CODEX_WORKDIR` | `~/clawd` | Working directory for tasks |
| `CODEX_TASK_DIR` | `~/.agent/codex/tasks` | Task storage |
| `CODEX_TASK_TIMEOUT` | `1800` | Max seconds per task |
| `CODEX_AGENT_DID` | - | Agent's Archon DID |

Same pattern for `GEMINI_*` and `HEX_*`.

## DID Authentication (TODO)

Currently stub auth (accepts all). Future: verify requests against `daemon-collective` group membership.

## Development

```bash
cd /home/sat/bin/agent-mcp
source .venv/bin/activate
python -m servers.codex_server  # Run directly for testing
```

## Related

- [Spec](/home/sat/clawd/specs/agent-mcp-protocol.md)
- [MCP Protocol](https://modelcontextprotocol.io)
- [Archon DID](https://github.com/archetech/archon)
