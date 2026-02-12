# Hexswarm - Agent Coordination Protocol

AI agents (Hex, Codex, Gemini) communicating via MCP with shared memory, context enrichment, and performance-based routing.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         HexMem (SQLite)                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ lessons  │  │  facts   │  │  events  │  │   performance    │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
        ▲                ▲                ▲
        │    shared_memory.py            │
        └────────────────┼───────────────┘
                         │
┌──────────────┐    ┌────┴───────┐    ┌──────────────┐
│     Hex      │    │  Context   │    │  Smart       │
│ (orchestrator)│◄───│  Builder   │◄───│  Delegate    │
├──────────────┤    └────────────┘    └──────────────┘
│ MCP Server   │
│              │
│ MCP Client ──┼──────────────────────────────────────┐
└──────────────┘                                      │
        │                                             │
        ▼                                             ▼
┌──────────────┐                              ┌──────────────┐
│    Codex     │                              │   Gemini     │
│   (coder)    │                              │ (researcher) │
├──────────────┤                              ├──────────────┤
│  MCP Server  │                              │  MCP Server  │
└──────────────┘                              └──────────────┘
```

## Quick Start

```bash
# Smart delegate (auto-selects best agent, enriches context)
/home/sat/bin/hexswarm/bin/smart-delegate.sh auto code "refactor the storage module"

# Shorthand wrapper
hs code "refactor the storage module"
hs research "find papers on LN routing"

# Task lifecycle visibility
hexswarm-status active              # Pending/running tasks
hexswarm-status recent 10           # Last 10 tasks
hexswarm-status stats               # Performance statistics
hexswarm-status agent codex         # Tasks for specific agent

# Query swarm intelligence
/home/sat/bin/hexswarm/bin/swarm-intel.sh lessons code
/home/sat/bin/hexswarm/bin/swarm-intel.sh best research
/home/sat/bin/hexswarm/bin/swarm-intel.sh context "debug the routing issue"

# Direct MCP calls
mcporter call codex.agent_info
mcporter call hex.agent_performance action=get_stats agent_name=codex
```

## Features

### Context Enrichment
When delegating tasks, relevant context is auto-injected from HexMem:
- **Lessons**: What we've learned doing similar work
- **Facts**: Known information about subjects in the task
- **Events**: Recent related activity

```bash
# Preview what context would be injected
/home/sat/bin/hexswarm/bin/swarm-intel.sh context "optimize channel fees"
```

### Shared Memory
Agents can share lessons and query collective knowledge:

```bash
# Share a lesson
mcporter call hex.agent_memory action=share_lesson agent_name=codex \
  domain=code lesson="Always validate inputs" context="Found bug in API handler"

# Search lessons
mcporter call hex.agent_memory action=search_lessons query="validation"

# Get lessons by domain
mcporter call hex.agent_memory action=get_lessons domain=code
```

### Performance Tracking
Track which agent performs best at which task types:

```bash
# Record performance
mcporter call hex.agent_performance action=record \
  agent_name=codex task_type=code success=true duration_seconds=45

# Get best agent for a task type
mcporter call hex.agent_performance action=best_for_task task_type=research

# View stats
mcporter call hex.agent_performance action=get_stats agent_name=codex
```

### Smart Routing
`smart-delegate.sh auto` picks the best agent based on:
1. Historical performance data (if available)
2. Skill-to-agent config matches (keywords, domains)
3. Default routing by task type (code→codex, research→gemini)

### Skill-to-Agent Mapping
Configure agent preferences in `config/agent-skills.json`:

```json
{
  "task_types": {
    "code": {"preferred": "codex", "fallback": "gemini"},
    "research": {"preferred": "gemini", "fallback": "codex"}
  },
  "domains": {
    "hive": {"preferred": "codex"},
    "lightning": {"preferred": "codex"},
    "papers": {"preferred": "gemini"}
  },
  "keywords": {
    "refactor": "codex",
    "research": "gemini"
  }
}
```

### Task Lifecycle Tracking
All tasks are tracked in HexMem (`hexswarm_tasks` table):

```bash
# View active tasks
hexswarm-status active

# View recent tasks with results
hexswarm-status recent 20

# View statistics
hexswarm-status stats

# View tasks for specific agent
hexswarm-status agent codex
```

Task states: `pending` → `running` → `completed` | `failed`

### Async Notifications
For tmux-based delegation, agents call `notify-done.sh` when complete:

```bash
# Check for completions
/home/sat/bin/hexswarm/bin/check-completions.sh
```

## MCP Tools (11 per agent)

| Tool | Description |
|------|-------------|
| `agent_info` | Identity, capabilities, status |
| `agent_status` | Availability, current task, queue depth |
| `submit_task` | Submit work (blocks until complete) |
| `task_status` | Check task progress |
| `task_result` | Get completed task output |
| `cancel_task` | Cancel pending/running task |
| `agent_resources` | Context/token tracking, capacity |
| `agent_memory` | Share/query lessons, facts, context |
| `agent_performance` | Track/query task performance |
| `check_notifications` | Check for async completions |

## Memory Actions

`agent_memory` supports these actions:

| Action | Description |
|--------|-------------|
| `log_event` | Record an event |
| `share_fact` | Record a fact (subject-predicate-object) |
| `get_context` | Search for relevant context |
| `record_handoff` | Record agent-to-agent handoff |
| `share_lesson` | Record a lesson learned |
| `get_lessons` | Get lessons by domain |
| `search_lessons` | Search lessons by keyword |
| `get_agent_lessons` | Get lessons by specific agent |

## File Structure

```
/home/sat/bin/hexswarm/
├── agent_mcp/
│   ├── __init__.py
│   ├── auth.py              # DID verification (stub)
│   ├── context_builder.py   # HexMem context enrichment
│   ├── notifications.py     # Async completion notifications
│   ├── protocol.py          # Task types and schemas
│   ├── resources.py         # Token/context tracking
│   ├── server.py            # Base MCP server
│   ├── shared_memory.py     # HexMem integration
│   └── storage.py           # Task persistence
├── servers/
│   ├── codex_server.py
│   ├── gemini_server.py
│   └── hex_server.py
├── bin/
│   ├── smart-delegate.sh    # Context-enriched delegation
│   ├── swarm-intel.sh       # Query swarm knowledge
│   ├── notify-done.sh       # Completion notifications
│   └── check-completions.sh # Check for notifications
└── README.md
```

## Task Storage

```
~/.agent/
├── codex/tasks/{pending,running,completed,failed}/
├── gemini/tasks/{pending,running,completed,failed}/
├── hex/tasks/{pending,running,completed,failed}/
└── notifications/{pending,processed}/
```

## Agent DIDs

| Agent | DID |
|-------|-----|
| Hex | `did:cid:bagaaieratn3qejd6mr4y2bk3nliriafoyeftt74tkl7il6bbvakfdupahkla` |
| Codex | `did:cid:bagaaierawhtwebyik523xjzhmxgfonrw56ssimutvr2surw3iypvgpjzehoa` |
| Gemini | `did:cid:bagaaieraafcrruni2vrpp4nmzhwpe2vnjjjuxj2lb5cew76jixjuil7fxoqa` |

## Configuration

Servers registered in `~/.mcporter/mcporter.json`:

```json
{
  "mcpServers": {
    "codex": {
      "type": "stdio",
      "command": "/home/sat/bin/hexswarm/bin/run-codex-server.sh",
      "env": {
        "CODEX_TASK_DIR": "/home/sat/.agent/codex/tasks",
        "CODEX_WORKDIR": "/home/sat/clawd"
      }
    }
  }
}
```

## Ecosystem

Hexswarm is part of an integrated agent autonomy stack:

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Autonomy Stack                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐   delegates   ┌──────────┐   falls back to    │
│  │ hexswarm │──────────────▶│  hexmux  │───────────────────▶│
│  │  (MCP)   │               │  (tmux)  │                    │
│  └────┬─────┘               └──────────┘                    │
│       │                                                      │
│       │ reads/writes                                         │
│       ▼                                                      │
│  ┌──────────┐                                               │
│  │  hexmem  │◀── structured memory (lessons, facts, events) │
│  │ (SQLite) │                                               │
│  └────┬─────┘                                               │
│       │                                                      │
│       │ backups, signing                                     │
│       ▼                                                      │
│  ┌──────────┐                                               │
│  │  archon  │◀── decentralized identity (DIDs, vaults)      │
│  │  (DID)   │                                               │
│  └──────────┘                                               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Component Roles

| Component | Purpose | GitHub |
|-----------|---------|--------|
| **hexswarm** | Agent coordination via MCP. Context enrichment, performance routing, shared memory. | [hexdaemon/hexswarm](https://github.com/hexdaemon/hexswarm) |
| **hexmux** | Tmux orchestration fallback. For agents needing write access or when MCP unavailable. | [hexdaemon/hexmux](https://github.com/hexdaemon/hexmux) |
| **hexmem** | Structured memory substrate. Identity, lessons, facts, events. Semantic search. | [hexdaemon/hexmem](https://github.com/hexdaemon/hexmem) |
| **archon-skill** | Decentralized identity operations. DIDs, credentials, vault backups. | [archetech/agent-skills](https://github.com/archetech/agent-skills) |

### Data Flow

1. **Delegation**: Hex delegates task via hexswarm MCP → if write needed, falls back to hexmux (tmux)
2. **Context**: hexswarm pulls relevant lessons/facts/events from hexmem before delegation
3. **Learning**: Agents record lessons to hexmem via `agent_memory` tool
4. **Identity**: Each agent has an Archon DID for future cryptographic auth
5. **Backup**: hexmem backs up to Archon vault for decentralized persistence

## External Links

- [Protocol Spec](/home/sat/clawd/specs/agent-mcp-protocol.md)
- [MCP Protocol](https://modelcontextprotocol.io)
- [Archon Network](https://archon.technology)
