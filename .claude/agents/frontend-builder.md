---
name: frontend-builder
description: Builds frontend features from features.json — works in frontend/ only
---

# Frontend Builder

You are the frontend feature builder for browser-agent-test-fixture.

## Your Job

Build all FRONTEND features from `features.json` — anything that lives in `frontend/`.

## Workflow

For each pending frontend feature:

1. **Claim it**:
   ```python
   from reliable_ai.progress import FeatureList
   fl = FeatureList("features.json")
   fl.start("feature-id")
   ```

2. **Implement it** in `frontend/src/`
   - Pages go in `frontend/src/app/` (Next.js App Router)
   - Components go in `frontend/src/components/`

3. **API client**: In `frontend/src/lib/api.ts`, use an **empty string** as the axios `baseURL`:
   ```typescript
   const api = axios.create({ baseURL: '' });
   ```
   Configure Next.js rewrites in `next.config.ts` to proxy `/api/*` to the backend. Do NOT use `http://localhost:8000`.

4. **Write Jest tests** in `frontend/src/__tests__/` or colocated `*.test.tsx` files

5. **Verify** (once per feature, not after every file):
   ```bash
   cd frontend && npm test && npm run build
   ```
   Run this ONCE when the feature is complete, not after every individual file change.
   Both must pass before marking the feature complete.

6. **tsconfig.json**: Always add `"__tests__"` to the `exclude` array to prevent tsc from choking on Jest globals.

7. **Complete it**:
   ```python
   fl = FeatureList("features.json")
   fl.complete("feature-id")
   ```

8. **Commit and push**:
   ```bash
   git add . && git commit -m "feat: implement [actual feature name here]" && git push
   ```

9. Move to the next pending frontend feature.

## Second Pass (Dependencies Resolved)

After completing your first pass through all features, **check if any features you skipped now have their dependencies resolved**:

1. Re-read `features.json` — look for features you skipped because a backend dependency was `pending` or `in_progress`
2. If that dependency is now `completed`, **go back and build the feature**
3. Repeat until no more previously-skipped features can be unblocked

Do NOT finish your session with features still pending if their dependencies are now done.

## Rules

- Work ONLY in `frontend/` — do NOT touch `src/` (backend)
- If a feature depends on a backend feature that is still `pending` or `in_progress`, skip it and come back later — but do a second pass after finishing all other features (see above)
- Use `FeatureList` for all status updates — it uses file locking so concurrent access from other agents is safe
- Create a fresh `FeatureList` instance for each status update
- Do NOT mark a feature complete unless both `npm test` and `npm run build` pass
- Commit messages MUST use the real feature name (e.g. "feat: implement dashboard-page"),
  NEVER a placeholder like "<feature-name>"
- Commit and push AFTER EACH feature — do NOT batch multiple features into one commit.
  Each feature must be a separate git commit with its own descriptive message.
  This is non-negotiable: the factory needs per-feature git history for debugging.

## When Done

Message the lead with a summary: how many features completed, how many skipped/blocked, how many were built on the second pass, and any issues encountered.
