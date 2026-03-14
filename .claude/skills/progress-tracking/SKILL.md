---
name: progress-tracking
description: Guide for using FeatureList state machine. Use when working with features.json, starting features, or completing work.
user-invocable: false
---

# Progress Tracking with FeatureList

## State Machine

Every feature follows this lifecycle:

```
pending → in_progress → completed
                     ↘ blocked (if external dependency needed)
```

**Rules:**
- You MUST call `start_feature()` before `complete_feature()` — completing a pending feature raises an error
- Features track who started them and when — this prevents two agents from working on the same feature
- Phase gates: if enabled, phase N+1 features won't appear until all phase N features are done

## Workflow (MCP Tools)

### 1. Find work
```
get_next_feature()
```
Returns the next pending feature with satisfied dependencies. If nothing returns, either all work is done or remaining features are blocked on dependencies.

### 2. Claim it
```
start_feature(id="feature-id")
```
Transitions from `pending` → `in_progress`. Uses file locking — safe for concurrent agents.

### 3. Track progress
```
touch_feature(id="feature-id", note="implemented 3 endpoints, tests passing")
```
Updates the `last_touched` timestamp and adds a progress note. Call this periodically so other agents (and the lead) can see what you're working on.

### 4. Complete it
```
complete_feature(id="feature-id", tests_pass=true, notes="Added CRUD endpoints + 5 tests")
```
Transitions from `in_progress` → `completed`. Requires `tests_pass=true`. The `notes` field survives context compaction — use it to record what was done.

### 5. Check overall progress
```
get_progress()
get_progress(include_completed=true)
```
Shows feature counts, phase status, and what's blocked.

## Shared State

Use `set_state` / `get_state` to share discovered values between agents:
```
set_state(key="DATABASE_URL", value="postgresql://...")
get_state(key="CODESPACE_NAME")
```

## Common Mistakes

- **Don't skip `start_feature()`** — calling `complete_feature()` on a pending feature will fail
- **Don't guess feature IDs** — use `get_next_feature()` to get the actual ID
- **Don't mark complete without passing tests** — `tests_pass=true` is required
- **Don't batch features** — complete one at a time, commit after each
