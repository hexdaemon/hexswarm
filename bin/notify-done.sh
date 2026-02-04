#!/bin/bash
# Called by agents to notify Hex that a task is complete
# Usage: notify-done.sh <task_id> <agent_name> <status> <summary>

TASK_ID="${1:?Usage: notify-done.sh <task_id> <agent_name> <status> <summary>}"
AGENT_NAME="${2:?Missing agent_name}"
STATUS="${3:-completed}"
SUMMARY="${4:-Task completed}"

cd /home/sat/bin/hexswarm
source .venv/bin/activate 2>/dev/null || true 2>/dev/null || true

python3 -c "
import sys
sys.path.insert(0, '/home/sat/bin/hexswarm')
from agent_mcp.notifications import notify_completion
path = notify_completion('$TASK_ID', '$AGENT_NAME', '$STATUS', '''$SUMMARY''')
print(f'✅ Notified: {path.name}')
"
