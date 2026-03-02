#!/bin/bash

# Compliance Logging Hook - Logs tool usage for observability
# Low overhead alternative to enforcement

TOOL_NAME="$1"
TOOL_ARGS="$2"

# Log tool usage for observability
echo "$(date -Iseconds) | $TOOL_NAME | direct_tool_usage" >> .claude/compliance.log

# Always allow - just observe
exit 0