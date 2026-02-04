#!/bin/bash
# Smart task delegation - picks best available agent
# Usage: delegate.sh <type> <description>
# Types: code, research, analysis, general

TYPE="${1:-general}"
shift
DESCRIPTION="$*"

if [ -z "$DESCRIPTION" ]; then
    echo "Usage: delegate.sh <type> <description>"
    echo "Types: code, research, analysis, general"
    exit 1
fi

# Check agent resources and pick best
RESOURCES=$(mcporter call codex.agent_resources 2>/dev/null)

# Get recommendations
BEST_CODE=$(echo "$RESOURCES" | jq -r '.recommendations.code')
BEST_RESEARCH=$(echo "$RESOURCES" | jq -r '.recommendations.research')

# Select agent based on task type
case "$TYPE" in
    code|analysis)
        AGENT="$BEST_CODE"
        ;;
    research)
        AGENT="$BEST_RESEARCH"
        ;;
    *)
        AGENT="$BEST_CODE"  # Default to code agent
        ;;
esac

# Check if agent is available
if [[ "$AGENT" == *"exhausted"* ]] || [ -z "$AGENT" ]; then
    echo "⚠️  All agents exhausted. Task requires manual handling."
    exit 1
fi

echo "📤 Delegating to $AGENT: $DESCRIPTION"
echo "---"

# Submit task
mcporter call "${AGENT}.submit_task" type="$TYPE" description="$DESCRIPTION"
