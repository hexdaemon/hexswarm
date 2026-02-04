#!/bin/bash
# Quick swarm intelligence queries
# Usage: swarm-intel.sh <command> [args...]

set -e

HEXSWARM_DIR="${HEXSWARM_DIR:-/home/sat/bin/hexswarm}"

show_help() {
    cat <<EOF
Hexswarm Intelligence Queries

Usage: swarm-intel.sh <command> [args...]

Commands:
  lessons [domain]       List lessons (optionally by domain: code, research, analysis)
  search <query>         Search lessons by keyword
  performance [agent]    Show agent performance stats
  best <task_type>       Get best agent for a task type
  context <description>  Preview what context would be injected for a task
  recent [limit]         Show recent agent events

Examples:
  swarm-intel.sh lessons code
  swarm-intel.sh search "debugging"
  swarm-intel.sh performance codex
  swarm-intel.sh best research
  swarm-intel.sh context "analyze the routing efficiency"
EOF
}

case "${1:-help}" in
    lessons)
        DOMAIN="${2:-general}"
        echo "📚 Lessons in domain: $DOMAIN"
        mcporter call hex.agent_memory action=get_lessons domain="$DOMAIN" limit=10 2>/dev/null | jq -r '.lessons[] | "[\(.source)] \(.lesson)"' 2>/dev/null || echo "No lessons found"
        ;;
    
    search)
        QUERY="${2:-}"
        if [ -z "$QUERY" ]; then
            echo "Usage: swarm-intel.sh search <query>"
            exit 1
        fi
        echo "🔍 Searching lessons for: $QUERY"
        mcporter call hex.agent_memory action=search_lessons query="$QUERY" limit=10 2>/dev/null | jq -r '.lessons[] | "[\(.domain)] \(.lesson)"' 2>/dev/null || echo "No matches found"
        ;;
    
    performance)
        AGENT="${2:-}"
        if [ -z "$AGENT" ]; then
            echo "📊 All Agent Performance:"
            for a in codex gemini hex; do
                echo ""
                echo "=== $a ==="
                mcporter call hex.agent_performance action=get_stats agent_name="$a" 2>/dev/null | jq -r '.stats | to_entries[] | "\(.key): \(.value.success)/\((.value.success + .value.failure)) (\((.value.success_rate * 100) | floor)%)"' 2>/dev/null || echo "No data"
            done
        else
            echo "📊 Performance for: $AGENT"
            mcporter call hex.agent_performance action=get_stats agent_name="$AGENT" 2>/dev/null | jq '.' 2>/dev/null || echo "No data"
        fi
        ;;
    
    best)
        TASK_TYPE="${2:-general}"
        echo "🎯 Best agent for '$TASK_TYPE' tasks:"
        mcporter call hex.agent_performance action=best_for_task task_type="$TASK_TYPE" available_agents='["codex", "gemini"]' 2>/dev/null | jq -r '"  \(.best_agent // "No recommendation (insufficient data)")"' 2>/dev/null
        ;;
    
    context)
        shift
        DESC="$*"
        if [ -z "$DESC" ]; then
            echo "Usage: swarm-intel.sh context <task description>"
            exit 1
        fi
        echo "📋 Context that would be injected:"
        echo ""
        python3 -c "
import sys
sys.path.insert(0, '$HEXSWARM_DIR')
from agent_mcp.context_builder import build_task_context
context = build_task_context('''$DESC''', 'general')
if context:
    print(context)
else:
    print('(No relevant context found)')
" 2>/dev/null
        ;;
    
    recent)
        LIMIT="${2:-5}"
        echo "📜 Recent agent events:"
        mcporter call hex.agent_memory action=get_context topic="agent:" limit="$LIMIT" 2>/dev/null | jq -r '.results[] | "[\(.timestamp)] [\(.event_type // .type)] \(.summary)"' 2>/dev/null || echo "No recent events"
        ;;
    
    help|--help|-h|*)
        show_help
        ;;
esac
