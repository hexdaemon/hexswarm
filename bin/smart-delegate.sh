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
    echo "Agents: codex, gemini, auto (picks best based on performance)"
    echo "Types: code, research, analysis, general"
    exit 1
fi

# Generate task ID
TASK_ID="task_$(date +%s)_$$"

# Check if task needs write access (use tmux instead of MCP)
NEEDS_WRITE=false
if echo "$DESCRIPTION" | grep -qiE "(create|write|modify|edit|update|save|add|implement|build|fix).*(file|script|code|function|class)"; then
    NEEDS_WRITE=true
fi

# Tmux targets
declare -A TMUX_TARGETS
TMUX_TARGETS[codex]="ssh_tmux:codex"
TMUX_TARGETS[gemini]="ssh_tmux:2.0"

# Auto-select agent based on performance if requested
if [ "$AGENT" = "auto" ]; then
    echo "🎯 Auto-selecting best agent for '$TYPE' tasks..."
    
    # Try to get best agent from performance data
    BEST=$(mcporter call hex.agent_performance action=best_for_task task_type="$TYPE" available_agents='["codex", "gemini"]' 2>&1 | jq -r '.best_agent // empty' 2>/dev/null || true)
    
    if [ -n "$BEST" ] && [ "$BEST" != "null" ]; then
        AGENT="$BEST"
        echo "   Selected: $AGENT (based on historical performance)"
    else
        # Default routing by task type
        case "$TYPE" in
            code)      AGENT="codex" ;;
            research)  AGENT="gemini" ;;
            analysis)  AGENT="gemini" ;;
            *)         AGENT="codex" ;;
        esac
        echo "   Selected: $AGENT (default for $TYPE tasks)"
    fi
fi

# Build enriched context from HexMem
echo "📚 Building context from HexMem..."
CONTEXT=$(python3 -c "
import sys
sys.path.insert(0, '$HEXSWARM_DIR')
from agent_mcp.context_builder import build_task_context
context = build_task_context('''$DESCRIPTION''', '$TYPE')
print(context)
" 2>/dev/null || echo "")

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
    
    RESULT=$(timeout 120 mcporter call "${AGENT}.submit_task" type="$TYPE" description="$ENRICHED_DESC" 2>&1) || true
    
    if echo "$RESULT" | grep -q '"status": "completed"'; then
        echo "✅ MCP completed"
        
        # Record performance
        DURATION=$(echo "$RESULT" | jq -r '.duration_seconds // 0' 2>/dev/null || echo "0")
        python3 -c "
import sys
sys.path.insert(0, '$HEXSWARM_DIR')
from agent_mcp.context_builder import record_agent_performance
record_agent_performance('$AGENT', '$TYPE', True, $DURATION)
" 2>/dev/null || true
        
        echo "$RESULT" | jq -r '.result // .summary // "Done"' 2>/dev/null || echo "$RESULT"
        exit 0
    fi
    
    # Record failure if it was a real failure (not just timeout/unavailable)
    if echo "$RESULT" | grep -q '"status": "failed"'; then
        python3 -c "
import sys
sys.path.insert(0, '$HEXSWARM_DIR')
from agent_mcp.context_builder import record_agent_performance
record_agent_performance('$AGENT', '$TYPE', False, 0)
" 2>/dev/null || true
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

FULL_PROMPT="$FULL_PROMPT

IMPORTANT: When you complete this task:
1. If you learned something useful, record it:
   mcporter call hex.agent_memory action=share_lesson agent_name=$AGENT domain=$TYPE lesson=\"What you learned\" context=\"Brief context\"
2. Notify completion:
   $HEXSWARM_DIR/bin/notify-done.sh $TASK_ID $AGENT completed \"Brief summary of what you did\""

# Send to tmux
tmux send-keys -t "$TMUX_TARGET" "$FULL_PROMPT" Enter

echo ""
echo "📤 Task sent with enriched context. Agent will notify when complete."
echo ""
echo "   To check status:  $HEXSWARM_DIR/bin/check-completions.sh"
echo "   To view agent:    tmux capture-pane -p -t $TMUX_TARGET | tail -30"
echo ""
echo "   No need to poll - just check back later or wait for notification."
