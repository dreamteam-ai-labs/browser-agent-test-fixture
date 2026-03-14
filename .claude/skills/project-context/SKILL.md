---
name: project-context
description: Current project status and shared state. Loaded automatically when agents need coordination context.
user-invocable: false
---

# Project Context

## Current Progress

!`python3 -c "from reliable_ai.progress import FeatureList; fl=FeatureList('features.json'); print(fl.format_for_context())" 2>/dev/null || echo "reliable-ai not installed yet — run get_progress() manually"`

## Shared State

!`python3 -c "from reliable_ai.progress import ProjectState; import json; ps=ProjectState('project-state.json'); print(json.dumps(ps.all(), indent=2))" 2>/dev/null || echo "No shared state yet"`

## Claude Code Version

!`claude --version 2>/dev/null || echo "unknown"`
