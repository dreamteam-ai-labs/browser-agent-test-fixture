#!/bin/bash

# Component Monitor Hook - Track Claude component usage
# Logs skill access, agent usage, plugin invocation, etc.

set -euo pipefail

LOG_FILE=".claude/component-usage.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Create log file if it doesn't exist
mkdir -p .claude
touch "$LOG_FILE"

# Parse hook input
input=$(cat)

# Extract tool information from input if available
tool_name=""
if echo "$input" | jq -e '.tool_name' &>/dev/null; then
    tool_name=$(echo "$input" | jq -r '.tool_name')
fi

# Log the tool usage
echo "[$TIMESTAMP] tool | $tool_name | executed" >> "$LOG_FILE"

# Check for specific component access patterns
if [[ "$input" == *".claude/skills/"* ]]; then
    skill_name=$(echo "$input" | grep -o '\.claude/skills/[^/]*' | sed 's|\.claude/skills/||' | head -1)
    echo "[$TIMESTAMP] skill | $skill_name | accessed" >> "$LOG_FILE"
fi

if [[ "$input" == *".claude/agents/"* ]]; then
    agent_name=$(echo "$input" | grep -o '\.claude/agents/[^/]*' | sed 's|\.claude/agents/||' | sed 's|\.md||' | head -1)
    echo "[$TIMESTAMP] agent | $agent_name | accessed" >> "$LOG_FILE"
fi

if [[ "$input" == *"reliable_ai"* ]]; then
    echo "[$TIMESTAMP] library | reliable_ai | imported or referenced" >> "$LOG_FILE"
fi

# Check for feature file access
if [[ "$input" == *"features.json"* ]]; then
    echo "[$TIMESTAMP] features | features.json | accessed" >> "$LOG_FILE"
fi

if [[ "$input" == *"environment_features.json"* ]]; then
    echo "[$TIMESTAMP] features | environment_features.json | accessed" >> "$LOG_FILE"
fi

# Always allow the tool to execute
echo '{"decision": "allow"}'