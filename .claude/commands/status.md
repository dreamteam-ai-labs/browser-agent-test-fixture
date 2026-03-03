# Project Status

Display current project status and next tasks.

## Instructions

Use the reliable-ai MCP tools to check progress:

1. Call `get_progress(include_completed=true)` to see all features and their status
2. Call `get_next_feature()` to identify the next available task
3. Display the results to the user

## Output Format

```
=== Project Status ===
Progress: 3/10 (30%)
Gaps remaining: 7

Next available:
  - feature-name: Description of what to do

Recent completions:
  - feature-1: Completed yesterday
  - feature-2: Completed today
```
