#!/bin/bash
# Smart delegation with context enrichment, performance-based routing, and async notifications
# Usage: smart-delegate.sh <agent|auto> <type> <description>

set -e

HEXSWARM_DIR="${HEXSWARM_DIR:-/home/sat/bin/hexswarm}"
AGENT="${1:-auto}"
TYPE="${2:-general}"
shift 2 2>/dev/null || true
DESCRIPTION="$*"

if [ -z "$DESCRIPTION" ]; then
    echo "Usage: smart-delegate.sh <agent|auto> <type> <description>"
    echo "Agents: claude-code (preferred), codex, gemini, auto (picks best)"
    echo "Types: code, research, analysis, general"
    exit 1
fi

# Validate agent name
case "$AGENT" in
    auto|claude-code|codex|gemini|hex) ;;
    *) echo "❌ Unknown agent: $AGENT"; exit 1 ;;
esac

# Validate task type
case "$TYPE" in
    code|research|analysis|general) ;;
    *) echo "❌ Unknown task type: $TYPE"; exit 1 ;;
esac

# Generate task ID (alphanumeric only for safety)
TASK_ID="task_$(date +%s)_$$"

# Base64 encode description for safe passing to Python
DESC_B64=$(echo -n "$DESCRIPTION" | base64 -w 0)

# Log delegation start to HexMem (events + daily log)
python3 << PYEOF
import sys, json, base64
sys.path.insert(0, '$HEXSWARM_DIR')
from agent_mcp.shared_memory import log_agent_event, log_daily_log

desc = base64.b64decode('$DESC_B64').decode('utf-8')
log_agent_event('hex', 'hexswarm_delegation', 'Delegated task', json.dumps({
  'task_id': '$TASK_ID',
  'requested_agent': '$AGENT',
  'task_type': '$TYPE',
  'description': desc[:500]
}, default=str))
log_daily_log('ops', f'hexswarm delegate: $TYPE → $AGENT', f'Task $TASK_ID: {desc[:200]}', source='hexswarm')
PYEOF



# Check if task needs write access (use tmux instead of MCP)
NEEDS_WRITE=false
if echo "$DESCRIPTION" | grep -qiE "(create|write|modify|edit|update|save|add|implement|build|fix).*(file|script|code|function|class)"; then
    NEEDS_WRITE=true
fi

# Tmux targets
declare -A TMUX_TARGETS
TMUX_TARGETS[claude-code]="ssh_tmux:claude"
TMUX_TARGETS[codex]="ssh_tmux:codex"
TMUX_TARGETS[gemini]="ssh_tmux:2.0"

# CLI commands for each agent
declare -A AGENT_CLI
AGENT_CLI[claude-code]="claude"
AGENT_CLI[codex]="codex"
AGENT_CLI[gemini]="gemini"

# Auto-select agent based on performance and config
if [ "$AGENT" = "auto" ]; then
    echo "🎯 Auto-selecting best agent for '$TYPE' tasks..."
    
    # Try to get best agent from performance data first
    BEST=$(mcporter call hex.agent_performance action=best_for_task task_type="$TYPE" available_agents='["claude-code", "codex", "gemini"]' 2>&1 | jq -r '.best_agent // empty' 2>/dev/null || true)
    
    if [ -n "$BEST" ] && [ "$BEST" != "null" ]; then
        AGENT="$BEST"
        echo "   Selected: $AGENT (based on historical performance)"
    else
        # Check config file for domain/keyword matches
        CONFIG_FILE="$HEXSWARM_DIR/config/agent-skills.json"
        if [ -f "$CONFIG_FILE" ]; then
            # Check for domain keywords in description
            DOMAIN_AGENT=$(python3 << PYEOF
import json, base64
desc = base64.b64decode('$DESC_B64').decode('utf-8').lower()
with open('$CONFIG_FILE') as f:
    config = json.load(f)

# Check keywords first
for keyword, agent in config.get('keywords', {}).items():
    if keyword in desc:
        print(agent)
        exit()

# Check domains
for domain, info in config.get('domains', {}).items():
    if domain in desc:
        print(info['preferred'])
        exit()

# Fall back to task type config
task_config = config.get('task_types', {}).get('$TYPE', {})
print(task_config.get('preferred', ''))
PYEOF
)
            if [ -n "$DOMAIN_AGENT" ]; then
                AGENT="$DOMAIN_AGENT"
                echo "   Selected: $AGENT (from skill config)"
            fi
        fi
        
        # Ultimate fallback - prefer claude-code
        if [ "$AGENT" = "auto" ]; then
            case "$TYPE" in
                code)      AGENT="claude-code" ;;
                research)  AGENT="gemini" ;;
                analysis)  AGENT="claude-code" ;;
                *)         AGENT="claude-code" ;;
            esac
            echo "   Selected: $AGENT (default for $TYPE tasks)"
        fi
    fi
fi

# Track task start in HexMem
python3 << PYEOF
import sys, base64
sys.path.insert(0, '$HEXSWARM_DIR')
from agent_mcp.shared_memory import track_task_start

desc = base64.b64decode('$DESC_B64').decode('utf-8')
track_task_start('$TASK_ID', '$AGENT', '$TYPE', desc)
PYEOF

# Build enriched context from HexMem
echo "📚 Building context from HexMem..."
CONTEXT=$(python3 << PYEOF
import sys, base64
sys.path.insert(0, '$HEXSWARM_DIR')
from agent_mcp.context_builder import build_task_context

desc = base64.b64decode('$DESC_B64').decode('utf-8')
context = build_task_context(desc, '$TYPE')
print(context)
PYEOF
) || CONTEXT=""

if [ -n "$CONTEXT" ]; then
    echo "   Found relevant context"
else
    echo "   No relevant context found"
fi

# Try MCP first (unless needs write)
if [ "$NEEDS_WRITE" = false ]; then
    echo "📡 Trying MCP ($AGENT)..."
    
    # Combine context with description
    ENRICHED_DESC="$DESCRIPTION"
    if [ -n "$CONTEXT" ]; then
        ENRICHED_DESC="$CONTEXT$DESCRIPTION"
    fi
    
    # Best-effort Archon-signed auth envelope (optional)
    AUTH_JSON=$(python3 << PYEOF
import sys, json, time, secrets, base64
sys.path.insert(0, '$HEXSWARM_DIR')
from agent_mcp.archon_utils import sign_json

desc = base64.b64decode('$DESC_B64').decode('utf-8')
payload = {
  'issuer': 'did:cid:bagaaieratn3qejd6mr4y2bk3nliriafoyeftt74tkl7il6bbvakfdupahkla',
  'type': 'hexswarmAuth',
  'created': time.time(),
  'nonce': secrets.token_hex(16),
  'task_type': '$TYPE',
  'agent': '$AGENT',
  'description': desc[:500]
}
signed = sign_json(payload)
print(json.dumps(signed or payload))
PYEOF
) || AUTH_JSON=""

    if [ -n "$AUTH_JSON" ]; then
        RESULT=$(timeout 120 mcporter call "${AGENT}.submit_task" type="$TYPE" description="$ENRICHED_DESC" auth="$AUTH_JSON" 2>&1) || true
    else
        RESULT=$(timeout 120 mcporter call "${AGENT}.submit_task" type="$TYPE" description="$ENRICHED_DESC" 2>&1) || true
    fi
    
    if echo "$RESULT" | grep -q '"status": "completed"'; then
        echo "✅ MCP completed"
        
        # Record performance and track completion in HexMem
        DURATION=$(echo "$RESULT" | jq -r '.duration_seconds // 0' 2>/dev/null || echo "0")
        SUMMARY=$(echo "$RESULT" | jq -r '.summary // "Task completed"' 2>/dev/null || echo "Task completed")
        python3 << PYEOF
import sys
sys.path.insert(0, '$HEXSWARM_DIR')
from agent_mcp.context_builder import record_agent_performance
from agent_mcp.shared_memory import track_task_complete

record_agent_performance('$AGENT', '$TYPE', True, $DURATION)
track_task_complete('$TASK_ID', True, '''$SUMMARY''', $DURATION)
PYEOF
        
        echo "$RESULT" | jq -r '.result // .summary // "Done"' 2>/dev/null || echo "$RESULT"
        exit 0
    fi
    
    # Record failure if it was a real failure (not just timeout/unavailable)
    if echo "$RESULT" | grep -q '"status": "failed"'; then
        ERROR_MSG=$(echo "$RESULT" | jq -r '.error // "Unknown error"' 2>/dev/null || echo "Unknown error")
        python3 << PYEOF
import sys
sys.path.insert(0, '$HEXSWARM_DIR')
from agent_mcp.context_builder import record_agent_performance
from agent_mcp.shared_memory import track_task_complete

record_agent_performance('$AGENT', '$TYPE', False, 0)
track_task_complete('$TASK_ID', False, 'Task failed', 0, '''$ERROR_MSG''')
PYEOF
    fi
    
    echo "⚠️  MCP unavailable or failed, using tmux..."
fi

# Fallback to tmux with async notification
TMUX_TARGET="${TMUX_TARGETS[$AGENT]}"

if [ -z "$TMUX_TARGET" ]; then
    echo "❌ No tmux target for $AGENT"
    exit 1
fi

# Check if tmux window exists
if ! tmux has-session -t "${TMUX_TARGET%%:*}" 2>/dev/null; then
    echo "❌ Tmux session not found: ${TMUX_TARGET%%:*}"
    exit 1
fi

echo "📺 Delegating to tmux ($TMUX_TARGET)..."
echo "   Task ID: $TASK_ID"

# Build prompt with context and completion instruction
FULL_PROMPT="$DESCRIPTION"

if [ -n "$CONTEXT" ]; then
    FULL_PROMPT="$CONTEXT$DESCRIPTION"
fi

COMPLETION_INSTRUCTIONS="

IMPORTANT: When you complete this task:
1. If you learned something useful, record it:
   mcporter call hex.agent_memory action=share_lesson agent_name=$AGENT domain=$TYPE lesson=\"What you learned\" context=\"Brief context\"
2. Notify completion:
   $HEXSWARM_DIR/bin/notify-done.sh $TASK_ID $AGENT completed \"Brief summary of what you did\""

FULL_PROMPT="${FULL_PROMPT}${COMPLETION_INSTRUCTIONS}"

# Send to tmux using a temp file to avoid shell escaping issues
TMPFILE=$(mktemp)
echo "$FULL_PROMPT" > "$TMPFILE"
tmux load-buffer "$TMPFILE"
tmux paste-buffer -t "$TMUX_TARGET"
tmux send-keys -t "$TMUX_TARGET" Enter
rm -f "$TMPFILE"

echo ""
echo "📤 Task sent with enriched context. Agent will notify when complete."
echo ""
echo "   To check status:  $HEXSWARM_DIR/bin/check-completions.sh"
echo "   To view agent:    tmux capture-pane -p -t $TMUX_TARGET | tail -30"
echo ""
echo "   No need to poll - just check back later or wait for notification."
