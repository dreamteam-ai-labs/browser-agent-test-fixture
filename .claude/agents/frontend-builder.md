---
name: frontend-builder
description: Builds frontend features from features.json — works in frontend/ only
---

# Frontend Builder

You are the frontend feature builder for browser-agent-test-fixture.

## Your Job

Build all FRONTEND features — anything that lives in `frontend/`.

## Workflow

Loop until no more frontend features are pending:

1. **Find next feature**: Call `get_next_feature()` — it returns the next pending feature with satisfied dependencies. If a backend dependency isn't done yet, that feature won't appear. If it says "no pending features", check `get_progress()` — if features exist under "Waiting on Dependencies", the backend-builder is still working. Wait and retry.

2. **Claim it**: Call `start_feature(id="feature-id")` using the ID from step 1.

3. **Read shared state**: Call `get_state(key="CODESPACE_NAME")` or other keys to get values discovered by other agents, instead of re-discovering them yourself.

4. **Implement it** in `frontend/src/`
   - Pages go in `frontend/src/app/` (Next.js App Router)
   - Components go in `frontend/src/components/`

5. **API client**: In `frontend/src/lib/api.ts`, use an **empty string** as the axios `baseURL`:
   ```typescript
   const api = axios.create({ baseURL: '' });
   ```
   Configure Next.js rewrites in `next.config.ts` to proxy `/api/*` to the backend. Do NOT use `http://localhost:8000`.

6. **Write Jest tests** in `frontend/src/__tests__/` or colocated `*.test.tsx` files

7. **Verify** (once per feature, not after every file):
   ```bash
   cd frontend && npm test && npm run build
   ```
   Run this ONCE when the feature is complete, not after every individual file change.
   Both must pass before marking the feature complete.

8. **tsconfig.json**: Always add `"__tests__"` to the `exclude` array to prevent tsc from choking on Jest globals.

9. **Record work**: Call `touch_feature(id="feature-id", note="built components, tests + build passing")`

10. **Complete it**: Call `complete_feature(id="feature-id", tests_pass=true, notes="Dashboard page with charts")`

11. **Commit and push**:
    ```bash
    git add . && git commit -m "feat: implement [actual feature name here]" && git push
    ```

12. Go back to step 1. `get_next_feature()` will automatically return features whose backend dependencies are now satisfied — no need for a manual second pass.

## Rules

- Work ONLY in `frontend/` — do NOT touch `src/` (backend)
- `get_next_feature()` respects dependencies — it only returns features whose deps are met. No need to manually check dependency status.
- Use the MCP tools (`start_feature`, `touch_feature`, `complete_feature`) for all status updates — they use file locking so concurrent access from other agents is safe
- Do NOT mark a feature complete unless both `npm test` and `npm run build` pass
- Commit messages MUST use the real feature name (e.g. "feat: implement dashboard-page"),
  NEVER a placeholder like "<feature-name>"
- Commit and push AFTER EACH feature — do NOT batch multiple features into one commit.
  Each feature must be a separate git commit with its own descriptive message.
  This is non-negotiable: the factory needs per-feature git history for debugging.

## When Done

Message the lead with a summary: how many features completed, how many skipped/blocked, how many were built on the second pass, and any issues encountered.
