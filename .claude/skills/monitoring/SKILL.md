---
name: Component Monitoring
description: Monitor and debug Claude component usage in reliable-ai projects
---

# Component Monitoring

## Summary
Track which reliable-ai components are being invoked during development sessions. Useful for debugging skills, agents, and session protocol execution.

## Monitoring Commands

### View Component Usage Log
```bash
# Real-time monitoring
tail -f .claude/component-usage.log

# View recent activity
tail -20 .claude/component-usage.log

# Filter specific components
grep "skill" .claude/component-usage.log
grep "agent" .claude/component-usage.log
grep "library" .claude/component-usage.log
```

### Component Inventory
```bash
# List available skills
ls .claude/skills/

# List available agents
ls .claude/agents/
```

## Log Format

Component usage is logged to `.claude/component-usage.log` in format:
```
[timestamp] component_type | component_name | action
```

**Examples:**
```
[2026-01-13 14:30:15] skill | web-app | accessed
[2026-01-13 14:30:16] agent | orchestrator | accessed
[2026-01-13 14:30:17] library | reliable_ai | imported
[2026-01-13 14:30:18] features | features.json | accessed
```

## Component Types Tracked

- **skill** - .claude/skills/ access
- **agent** - .claude/agents/ access
- **library** - reliable-ai library usage
- **features** - features.json access
- **tool** - General tool usage
- **session** - Session protocol events

## Debugging Common Issues

**Skills Not Loading:**
```bash
# Check skill access patterns
grep "skill" .claude/component-usage.log

# Verify skill files exist
find .claude/skills/ -name "*.md"
```

**Agent Patterns Not Working:**
```bash
# Check agent usage
grep "agent" .claude/component-usage.log

# Check reliable-ai library access
grep "reliable_ai" .claude/component-usage.log
```

## Manual Component Testing

**Test Skills Access:**
```bash
# Ask Claude to reference a specific skill
# "Use the web-app skill to help with React development"
```

**Test Agent Patterns:**
```bash
# Ask Claude to use agent patterns
# "Use the orchestrator pattern for this complex task"
```

## Analysis

**Session Overview:**
```bash
# Count component usage by type
awk -F'|' '{print $2}' .claude/component-usage.log | sort | uniq -c

# Show chronological component access
cat .claude/component-usage.log
```

**Performance Analysis:**
```bash
# Check for repeated access patterns
awk -F'|' '{print $2 " | " $3}' .claude/component-usage.log | sort | uniq -c | sort -nr
```

This monitoring helps understand what components Claude is actually using vs what's configured in the project.