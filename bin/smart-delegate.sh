#!/bin/bash
# Smart delegation with MCP-first, tmux fallback, async notifications
# Usage: smart-delegate.sh <agent> <type> <description>

set -e

AGENT="${1:-codex}"
TYPE="${2:-general}"
shift 2 2>/dev/null || true
DESCRIPTION="$*"

if [ -z "$DESCRIPTION" ]; then
    echo "Usage: smart-delegate.sh <agent> <type> <description>"
    echo "Agents: codex, gemini"
    echo "Types: code, research, analysis, general"
    exit 1
fi

# Generate task ID
TASK_ID="task_$(date +%s)_$$"

# Check if task needs write access (use tmux instead of MCP)
NEEDS_WRITE=false
if echo "$DESCRIPTION" | grep -qiE "(create|write|modify|edit|update|save|add).*(file|script|code)"; then
    NEEDS_WRITE=true
fi

# Tmux targets
declare -A TMUX_TARGETS
TMUX_TARGETS[codex]="ssh_tmux:codex"
TMUX_TARGETS[gemini]="ssh_tmux:2.0"

# Try MCP first (unless needs write)
if [ "$NEEDS_WRITE" = false ]; then
    echo "📡 Trying MCP ($AGENT)..."
    
    RESULT=$(timeout 120 mcporter call "${AGENT}.submit_task" type="$TYPE" description="$DESCRIPTION" 2>&1) || true
    
    if echo "$RESULT" | grep -q '"status": "completed"'; then
        echo "✅ MCP completed"
        echo "$RESULT" | jq -r '.result // .summary // "Done"' 2>/dev/null || echo "$RESULT"
        exit 0
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

# Build prompt with completion instruction
FULL_PROMPT="$DESCRIPTION

IMPORTANT: When you complete this task, run this command to notify me:
/home/sat/bin/hexswarm/bin/notify-done.sh $TASK_ID $AGENT completed \"Brief summary of what you did\""

# Send to tmux
tmux send-keys -t "$TMUX_TARGET" "$FULL_PROMPT" Enter

echo ""
echo "📤 Task sent. Agent will notify when complete."
echo ""
echo "   To check status:  /home/sat/bin/hexswarm/bin/check-completions.sh"
echo "   To view agent:    tmux capture-pane -p -t $TMUX_TARGET | tail -30"
echo ""
echo "   No need to poll - just check back later or wait for notification."
