#!/bin/bash
# Check for task completion notifications
# Usage: check-completions.sh [agent_name]

AGENT="${1:-}"

cd /home/sat/bin/hexswarm
source .venv/bin/activate 2>/dev/null || true 2>/dev/null || true

python3 -c "
import sys
sys.path.insert(0, '/home/sat/bin/hexswarm')
from agent_mcp.notifications import check_notifications
import json

agent = '$AGENT' if '$AGENT' else None
notifications = check_notifications(agent)

if not notifications:
    print('No pending notifications')
else:
    for n in notifications:
        print(f\"📬 {n['agent_name']}: {n['status']} - {n['summary']}\")
    print()
    print(json.dumps(notifications, indent=2, default=str))
"
