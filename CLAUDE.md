# browser-agent-test-fixture

A project management app with auth, projects, and tasks — used to validate factory templates.

## CRITICAL: Session Startup Protocol

**Every Claude session MUST start by executing this protocol:**

1. **Read progress state:**
   ```
   Read: environment_features.json
   Read: features.json
   Read: claude-progress.txt
   ```

2. **Review git status:**
   ```
   git status
   git log --oneline -5
   ```

3. **Verify working state:**
   - Check if last session left incomplete work
   - Run `pytest` to ensure tests pass
   - If broken state, fix before proceeding

4. **Select next task:**
   - **FIRST**: Complete ALL features in `environment_features.json` (Phase 0)
   - **THEN**: Find first `"status": "pending"` feature in `features.json`
   - Do NOT skip ahead to "more interesting" features
   - Do NOT declare project complete if pending features remain
   - Environment must be 100% validated before application development

5. **Update progress tracking:**
   - Mark selected feature as `"in_progress"` in `features.json`
   - Log session start in `claude-progress.txt`
   - Log component usage to `claude-component-log.txt` (append format: timestamp | component | action)

6. **Start autonomous development** using agent teams (see below).

---

## Agent Teams (MANDATORY)

Agent teams are enabled (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`). You MUST use the following team structure. Custom agent definitions are in `.claude/agents/`.

### Team Structure

| Agent | Role | Scope | When to spawn |
|-------|------|-------|---------------|
| **You (lead)** | Build Phase 0 + Phase 1 foundations, coordinate | Everything | Always — you are the main session |
| **backend-builder** | Build remaining backend features | `src/`, `tests/` only | After Phase 1 foundations complete |
| **frontend-builder** | Build remaining frontend features | `frontend/` only | After Phase 1 foundations complete |
| **qa-tester** | Functional testing of every feature + browser smoke test | Read-only, runs commands | After all features built |

### Workflow

1. **Phase 0 + Phase 1** (you, sequential): Complete ALL environment features, then build foundations — database schema/migrations, auth module, frontend project setup (`npx create-next-app@14` — use Next.js 14 for stability; do NOT use latest/canary). Use `next.config.mjs` (not `.ts` — Next.js 14 doesn't support TypeScript config). Commit and push after each feature. IMPORTANT: The database-schema feature must define ALL tables needed by ALL features in the app (read the full features.json to identify every table). Later features should NOT need to create new tables — the schema should be complete from Phase 1.

2. **Phase 2+** (parallel agents): Spawn both builders:
   ```
   Spawn agent: backend-builder
   Spawn agent: frontend-builder
   ```
   They will claim features from `features.json`, build, test, commit, and push independently. Wait for both to finish.

   **Audit sub-agent commits** (before spawning QA): After both builders finish, verify their work:
   ```bash
   git log --oneline | head -60
   ```
   Check: each feature has its own commit with a real feature name (not `<feature-name>` or batched).
   If any agent batched multiple features into one commit, split them before proceeding.

3. **QA** (after builders done): Spawn the QA tester:
   ```
   Spawn agent: qa-tester
   ```
   It registers a user, tests every feature's CRUD operations with real data, runs the browser
   smoke test, and reports critical issues. If there are ANY critical issues (including browser
   smoke test failures), fix them and ask it to retest. Do NOT declare the build complete until
   QA reports zero critical issues.

4. **Final pass** (you): Run `pytest -v && cd frontend && npm test && npm run build`. Verify all routers are registered in `main.py`. Commit any remaining fixes.

### Coordination Rules

- **`features.json` is the source of truth** — all agents use `FeatureList` for atomic status updates
- **Concurrent access is safe**: `FeatureList` uses file locking. Create a fresh instance for each status update (don't hold references across long operations)
- **No overlapping files**: backend-builder owns `src/` + `tests/`, frontend-builder owns `frontend/`. You (lead) handle `main.py` router registration and cross-cutting concerns
- **Commit per feature**: Every agent MUST commit and push after completing EACH feature — never batch multiple features into one commit. This is critical for debugging and rollback. Each commit = exactly one feature.

---

## Feature Development Workflow

### Reading Features
```python
from reliable_ai.progress import FeatureList

fl = FeatureList("features.json")
next_feature = fl.get_next_pending()
print(f"Next: {next_feature.name if next_feature else 'All complete!'}")

# List all features
for f in fl.all_features:
    print(f"  [{f.status}] {f.id}: {f.name}")

# Progress summary
print(fl.get_progress())
```

### Completing Features
**NEVER mark a feature as completed unless:**
- All code is written
- Tests pass (`pytest -v`)
- No TODO comments left

```python
from reliable_ai.progress import FeatureList

fl = FeatureList("features.json")
fl.start("feature-id")          # Mark as in_progress
# ... build the feature ...
fl.complete("feature-id")       # Mark as completed
fl.save()
```

**NOTE**: Use `fl.all_features` to iterate features. Do NOT use `fl.features` (it does not exist).

---

## reliable-ai Integration

This project uses `reliable-ai` for feature tracking and coordination:

```python
from reliable_ai.progress import FeatureList

fl = FeatureList("features.json")
next_feature = fl.get_next_pending()
fl.start(next_feature.id)
# ... build the feature ...
fl.complete(next_feature.id)
```

FeatureList uses file locking for safe concurrent access from multiple agents.

---

## Key Files

| File | Purpose |
|------|---------|
| `src/fixture/main.py` | Backend application entry point (FastAPI) |
| `frontend/src/app/` | Frontend pages (Next.js App Router) |
| `frontend/src/components/` | Reusable React components |
| `frontend/src/lib/api.ts` | API client for backend communication |
| `tests/` | Backend test suite (pytest) |
| `frontend/src/` | Frontend tests (npm test) |
| `features.json` | Feature/gap tracking (drives development) |
| `claude-progress.txt` | Session progress log |

---

## Development Guidelines

### Code Style
- Follow PEP 8
- Use type hints on all functions
- Write docstrings for public APIs
- Keep functions focused and small

### Testing
- Write tests for all new features
- Run `pytest -v` before marking complete
- Maintain >80% code coverage
- **Integration testing is mandatory for auth and frontend features**: Start the backend (`python3 -m uvicorn src.fixture.main:app --port 8000 &`), then verify signup and login work end-to-end via HTTP requests (e.g. `httpx.post("http://localhost:8000/api/auth/register", json={...})`). A feature is NOT complete if it only passes unit tests but fails against the running API.
- **Frontend tests**: Run `cd frontend && npm test` for component tests. If no test runner is configured, set up Jest + React Testing Library and write tests for key user flows (login form submission, registration, dashboard rendering).
- **Frontend build validation**: After adding or modifying frontend pages, run `cd frontend && NODE_ENV=production npm run build` to verify the production build succeeds. `next start` only serves pre-built pages — any page added after the last build will 404 in production.
- **Database schema validation**: If using a shared database that may have pre-existing tables from other projects, verify your ORM models match the actual schema after creating them. Mismatches between SQLAlchemy models and the real DB columns cause 409 Conflict or 500 errors at runtime. Run `ALTER TABLE ... ADD COLUMN` migrations for any missing columns rather than assuming the DB is empty.
- **Frontend tsconfig**: When creating `frontend/tsconfig.json`, always add `"__tests__"` to the `exclude` array. Jest test files use globals (`describe`, `it`, `expect`) that are not recognized by tsc without `@types/jest` in the compilation scope. Excluding test dirs from tsconfig prevents build failures while keeping Jest happy via its own config.
- **Frontend API client**: In `frontend/src/lib/api.ts`, use an **empty string** as the axios `baseURL` (NOT `http://localhost:8000`). Configure Next.js rewrites in `next.config.ts` to proxy `/api/*` requests to the backend. This ensures the app works in all environments (local dev, Codespaces, deployed). Hardcoding `localhost:8000` breaks when the app is accessed remotely because the browser sends requests to the user's local machine instead of the server.

### Committing
- Commit and push after each completed feature (`git add . && git commit -m "..." && git push`)
- Use descriptive messages: `feat: implement user authentication`
- Update `claude-progress.txt` before committing

---

## Commands

Custom slash commands are in `.claude/commands/`:
- `/status` - Check feature progress

---

## Dependencies

- `reliable-ai` - Core agent patterns and utilities
- See `pyproject.toml` for full list