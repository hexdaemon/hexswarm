#!/bin/bash
# Called by agents to notify Hex that a task is complete
# Usage: notify-done.sh <task_id> <agent_name> <status> <summary>

TASK_ID="${1:?Usage: notify-done.sh <task_id> <agent_name> <status> <summary>}"
AGENT_NAME="${2:?Missing agent_name}"
STATUS="${3:-completed}"
SUMMARY="${4:-Task completed}"

cd /home/sat/bin/hexswarm
source .venv/bin/activate 2>/dev/null || true

# Base64 encode summary for safe passing to Python
SUMMARY_B64=$(echo -n "$SUMMARY" | base64 -w 0)

python3 << PYEOF
import sys, base64
sys.path.insert(0, '/home/sat/bin/hexswarm')
from agent_mcp.notifications import notify_completion
from agent_mcp.shared_memory import track_task_complete

summary = base64.b64decode('$SUMMARY_B64').decode('utf-8')
success = '$STATUS' == 'completed'

# Create notification file
path = notify_completion('$TASK_ID', '$AGENT_NAME', '$STATUS', summary)
print(f'✅ Notified: {path.name}')

# Also track in HexMem for persistent visibility
track_task_complete('$TASK_ID', success, summary, 0)
PYEOF
