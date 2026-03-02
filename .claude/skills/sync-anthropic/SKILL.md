# Sync Anthropic Best Practices

This skill syncs reliable-ai with the latest Anthropic best practices, features, and capabilities.

## When to Use

- After seeing announcements of new Claude features
- Periodically (weekly/monthly) to check for updates
- When starting a new development cycle
- When you want to ensure reliable-ai is current with upstream

## Sources Tracked

1. **Claude Code Changelog** - CLI features, hooks, agents
   - URL: https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md

2. **Anthropic Engineering Articles** - Best practices
   - URL: https://www.anthropic.com/engineering

3. **Claude API Updates** - Model capabilities
   - URL: https://docs.anthropic.com/en/docs/about-claude/models

## Workflow

### Step 1: Fetch Latest Features

```python
from reliable_ai.sync import FeatureTracker, FeatureSource, FeatureCategory, UpstreamFeature

tracker = FeatureTracker("feature-tracking.json")

# Add features from changelog analysis
tracker.add_feature(UpstreamFeature(
    id="thinking-mode",
    name="Thinking Mode",
    description="Extended reasoning for Opus 4.5",
    source=FeatureSource.CLAUDE_CODE,
    category=FeatureCategory.THINKING,
))
```

### Step 2: Analyze Gaps

```python
analysis = tracker.analyze_gaps()
print(f"Coverage: {analysis.coverage_percentage:.1f}%")
print(f"High priority gaps: {len(analysis.high_priority_gaps)}")
```

### Step 3: Create Adoption Tasks

```python
for feature_id in ["thinking-mode", "custom-agents", "plan-mode"]:
    tracker.create_adoption_task(feature_id, priority=8)
```

### Step 4: Generate Report

```python
report = tracker.generate_adoption_report()
print(report)
```

## Priority Features to Track

| Feature | Category | Priority | Notes |
|---------|----------|----------|-------|
| Thinking Mode | thinking | 9 | Aligns with Think tool |
| Custom Agents | agent-patterns | 9 | System prompts, tool restrictions |
| Plan Mode | thinking | 8 | Structured planning |
| Hook Systems | permissions | 7 | Permission, stop hooks |
| Background Agents | agent-patterns | 7 | Parallel execution |
| Named Sessions | session | 6 | Persistence |
| LSP Tool | integration | 5 | Code intelligence |

## Implementation Checklist

When adopting a new feature:

1. [ ] Understand the feature from source documentation
2. [ ] Identify which reliable-ai module it maps to
3. [ ] Design the implementation (use /plan mode)
4. [ ] Implement with tests
5. [ ] Verify integration tests pass (`pytest tests/test_integration/ -v`)
6. [ ] Update feature-tracking.json status

## Commands

```bash
# Fetch and analyze
python -c "
from reliable_ai.sync import FeatureTracker
tracker = FeatureTracker('feature-tracking.json')
print(tracker.generate_adoption_report())
"

# Check specific feature
python -c "
from reliable_ai.sync import FeatureTracker
tracker = FeatureTracker('feature-tracking.json')
task = tracker.tasks.get('thinking-mode')
print(f'{task.feature_name}: {task.status.value}' if task else 'Not tracked')
"
```

## Integration with features.json

When a feature is adopted:

1. Add to features.json as a new feature
2. Implement following gap-driven development
3. Update feature-tracking.json to mark as IMPLEMENTED
4. Document in CLAUDE.md if it changes workflow
