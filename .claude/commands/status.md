# Project Status

Display current project status and next tasks.

## Instructions

1. Read `features.json` to see all features and their status
2. Calculate progress (completed vs total)
3. Identify next available gap (pending feature with met dependencies)
4. Display summary

## Process

```python
from reliable_ai.progress import FeatureList

features = FeatureList("features.json")

# Count by status
total = len(features.features)
completed = len([f for f in features.features if f.status.value == "completed"])
pending = len([f for f in features.features if f.status.value == "pending"])

print(f"Progress: {completed}/{total} ({100*completed//total if total else 0}%)")
print(f"Pending: {pending}")

# Next task
next_feature = features.get_next_pending()
if next_feature:
    print(f"Next: {next_feature.name}")
else:
    print("All done!")
```

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