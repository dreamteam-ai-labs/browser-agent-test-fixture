#!/bin/bash
# Claude Code Issue Detection Hook
# Automatically creates GitHub issues when Claude encounters problems

# Exit if not in a git repo or if gh CLI not available
if ! git rev-parse --git-dir &>/dev/null || ! command -v gh &>/dev/null; then
    exit 0
fi

# Read the last Claude message from stdin
MESSAGE=$(cat)

# Define patterns that indicate issues Claude encountered
ISSUE_PATTERNS=(
    "I need to fix"
    "This is a problem"
    "Missing feature"
    "Should be"
    "Gap in"
    "This doesn't work"
    "We need to"
    "I'll need to refactor"
    "This is broken"
    "Architecture issue"
    "Design problem"
    "Integration issue"
    "Can't implement"
    "Blocked by"
    "Missing pattern"
    "API is unclear"
    "Documentation unclear"
    "Need to restructure"
)

# Check if message contains any issue patterns
FOUND_ISSUE=false
MATCHED_PATTERN=""

for pattern in "${ISSUE_PATTERNS[@]}"; do
    if echo "$MESSAGE" | grep -qi "$pattern"; then
        FOUND_ISSUE=true
        MATCHED_PATTERN="$pattern"
        break
    fi
done

# Exit early if no issue detected
if [ "$FOUND_ISSUE" != "true" ]; then
    exit 0
fi

# Extract project info
PROJECT_NAME="browser-agent-test-fixture"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "main")

# Determine issue category based on content
CATEGORY="general"
LABELS="claude-detected"

if echo "$MESSAGE" | grep -qi "reliable.ai\|agent pattern\|library"; then
    CATEGORY="library-issue"
    LABELS="claude-detected,library-upstream"
elif echo "$MESSAGE" | grep -qi "template\|devcontainer\|setup"; then
    CATEGORY="template-issue"
    LABELS="claude-detected,template-upstream"
elif echo "$MESSAGE" | grep -qi "architecture\|design\|structure"; then
    CATEGORY="architecture"
    LABELS="claude-detected,architecture"
elif echo "$MESSAGE" | grep -qi "integration\|api\|interface"; then
    CATEGORY="integration"
    LABELS="claude-detected,integration"
fi

# Generate issue title
TITLE="Claude Issue: ${MATCHED_PATTERN} (${TIMESTAMP})"

# Generate issue body with context
BODY="## Claude-Detected Issue

**Timestamp:** ${TIMESTAMP}
**Project:** ${PROJECT_NAME}
**Branch:** ${CURRENT_BRANCH}
**Category:** ${CATEGORY}
**Trigger Pattern:** \"${MATCHED_PATTERN}\"

## Claude's Message

\`\`\`
${MESSAGE}
\`\`\`

## Context

- **Repository:** $(git config --get remote.origin.url 2>/dev/null || echo 'Unknown')
- **Last Commit:** $(git log -1 --oneline 2>/dev/null || echo 'No commits')
- **Working Directory:** $(pwd)

## Next Steps

- [ ] **Review** - Is this a real issue that needs attention?
- [ ] **Categorize** - Should this be escalated upstream?
  - [ ] **reliable-ai library** - Missing patterns, API issues
  - [ ] **template system** - Template generation problems
  - [ ] **project-specific** - Local architectural decisions
- [ ] **Action** - Implement fix or create upstream issue
- [ ] **Close** - Mark as resolved

## Auto-Generated
This issue was automatically created by Claude Code when it detected a potential problem during development.
"

# Self-healing: Create missing GitHub labels if they don't exist
create_missing_labels() {
    local required_labels=("claude-detected" "library-upstream" "template-upstream" "architecture" "integration")
    local label_configs=(
        "claude-detected:Auto-created by Claude:FF6B6B"
        "library-upstream:Issue in upstream library:FFA500"
        "template-upstream:Issue in template system:FFA500"
        "architecture:Architecture or design issue:9C27B0"
        "integration:Integration or API issue:2196F3"
    )

    for config in "${label_configs[@]}"; do
        IFS=':' read -r label_name description color <<< "$config"

        # Check if label exists (exit code 0 if found)
        if ! gh label list --search "$label_name" --limit 100 2>/dev/null | grep -q "^$label_name"; then
            # Create the label (suppress output, allow failure)
            gh label create "$label_name" \
                --description "$description" \
                --color "$color" \
                >/dev/null 2>&1 || true
        fi
    done
}

# Ensure required labels exist before creating issue
create_missing_labels

# Create the issue (suppress output to avoid cluttering Claude's interface)
gh issue create \
    --title "$TITLE" \
    --body "$BODY" \
    --label "$LABELS" \
    >/dev/null 2>&1

# Optional: Log to a local file for debugging
echo "[$(date)] Created issue: $TITLE" >> .claude/issue-log.txt

exit 0