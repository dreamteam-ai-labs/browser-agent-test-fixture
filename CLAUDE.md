# browser-agent-test-fixture

A project management app with auth, projects, and tasks — used to validate factory templates.

## CRITICAL: Session Startup Protocol

**Every Claude session MUST start by executing this protocol:**

1. **Read progress state:**
   ```
   Read: environment_features.json
   Read: claude-progress.txt
   Read: qa-report.json (if it exists — contains previous QA iterations with failures to fix)
   Call MCP tool: get_progress()
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
   - **THEN**: Call `get_next_feature()` to get the next pending feature
   - **IF qa-report.json exists with critical issues**: Fix those issues before building new features — read the `latest` entry's `summary.critical_issues` array and address each one
   - Do NOT skip ahead to "more interesting" features
   - Do NOT declare project complete if pending features remain
   - Environment must be 100% validated before application development

5. **Update progress tracking:**
   - Call `start_feature(id="...")` to mark the selected feature as in_progress
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

1. **Phase 0 + Phase 1** (you, sequential): Complete ALL environment features, then build foundations — database schema/migrations, auth module, frontend project setup (`npx create-next-app@14` — use Next.js 14 for stability; do NOT use latest/canary). Commit and push after each feature. IMPORTANT: The database-schema feature must define ALL tables needed by ALL features in the app (read the full features.json to identify every table). Later features should NOT need to create new tables — the schema should be complete from Phase 1.
   - **Environment features (`tests/integration/`)**: Run these tests directly with `pytest tests/integration/test_*.py -v`.

2. **Phase 2+** (parallel agents): Spawn both builders:
   ```
   Spawn agent: backend-builder
   Spawn agent: frontend-builder
   ```
   They will claim features via `get_next_feature()` and `start_feature()`, build, test, commit, and push independently. Wait for both to finish.

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

- **`features.json` is the source of truth** — all agents use the reliable-ai MCP tools for atomic status updates
- **Tag every feature**: Each feature in features.json should have a `tags` array: `["backend"]` for API-only features, `["ui", "frontend"]` for UI-only features, or `["backend", "ui"]` for full-stack features. Tags drive UI test enforcement — QA will flag UI-tagged features that lack component tests as CRITICAL.
- **Concurrent access is safe**: The MCP server uses file locking. Multiple agents can call `start_feature`, `complete_feature` etc. simultaneously
- **Share discovered values**: Use `set_state(key, value)` to share environment info (e.g. `CODESPACE_NAME`, `DATABASE_URL`) and `get_state(key)` to read it — avoids agents re-discovering what another agent already found
- **No overlapping files**: backend-builder owns `src/` + `tests/`, frontend-builder owns `frontend/`. You (lead) handle `main.py` router registration and cross-cutting concerns
- **Commit per feature**: Every agent MUST commit and push after completing EACH feature — never batch multiple features into one commit. This is critical for debugging and rollback. Each commit = exactly one feature.

---

## Feature Development Workflow

### Reading Features

Use the reliable-ai MCP tools (available as `mcp__reliable-ai__*` in your tool list):

```
get_progress()                    → Markdown summary with all feature IDs, descriptions, deps
get_next_feature()                → Next pending feature ready to start
get_state(key="CODESPACE_NAME")   → Read shared project state
```

### Working on Features

```
start_feature(id="feature-id")                        → Mark as in_progress (MUST call first)
touch_feature(id="feature-id", note="built endpoints") → Record work iteration
complete_feature(id="feature-id", tests_pass=true)     → Mark as completed
```

### Sharing Discovered Values

When you discover environment values, share them so other agents don't have to re-discover:

```
set_state(key="CODESPACE_NAME", value="codespaces-abc123")
set_state(key="DATABASE_URL", value="postgresql://...")
```

Other agents read these with `get_state(key="CODESPACE_NAME")`.

### Completion Rules

**NEVER mark a feature as completed unless:**
- All code is written
- Tests pass (`pytest -v`)
- No TODO comments left

The MCP server enforces: `start_feature` must be called before `complete_feature`. Attempting to complete a feature that hasn't been started returns an error.

---

## reliable-ai Integration

This project uses reliable-ai's MCP server for feature tracking and coordination. The server is registered in `.mcp.json` and provides 7 tools:

| Tool | Purpose |
|------|---------|
| `get_progress` | Project status with all feature IDs and dependencies |
| `get_next_feature` | Next pending feature (respects deps and phases) |
| `start_feature` | Mark feature as in_progress |
| `touch_feature` | Record work iteration |
| `complete_feature` | Mark feature as completed (enforces start-before-complete) |
| `get_state` | Read shared project state |
| `set_state` | Write shared project state |

All tools use file locking for safe concurrent access from multiple agents.

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
- **FastAPI lifecycle**: Use `lifespan` context manager (NOT `@app.on_event("startup")` which is deprecated). Example: `@asynccontextmanager async def lifespan(app): yield` then `app = FastAPI(lifespan=lifespan)`

### Testing
- Write tests for all new features
- Run `pytest -v` before marking complete
- Maintain >80% code coverage
- **Integration testing is mandatory for auth and frontend features**: Start the backend (`python3 -m uvicorn src.fixture.main:app --port 8000 &`), then verify signup and login work end-to-end via HTTP requests (e.g. `httpx.post("http://localhost:8000/api/auth/register", json={...})`). A feature is NOT complete if it only passes unit tests but fails against the running API.
- **Frontend tests**: Run `cd frontend && npm test` for component tests. If no test runner is configured, set up Jest + React Testing Library and write tests for key user flows (login form submission, registration, dashboard rendering).
- **Frontend build validation**: After adding or modifying frontend pages, run `cd frontend && NODE_ENV=production npm run build` to verify the production build succeeds. `next start` only serves pre-built pages — any page added after the last build will 404 in production.
- **Database schema validation**: If using a shared database that may have pre-existing tables from other projects, verify your ORM models match the actual schema after creating them. Mismatches between SQLAlchemy models and the real DB columns cause 409 Conflict or 500 errors at runtime. Run `ALTER TABLE ... ADD COLUMN` migrations for any missing columns rather than assuming the DB is empty.
- **Frontend API client**: API calls from frontend must work without CORS errors. Do NOT hardcode `localhost:8000` — it breaks when the app is accessed remotely. Use Next.js rewrites or an equivalent proxy approach.
- **Frontend jest.config**: When creating `jest.config.js` or `jest.config.ts`, never define the same key twice (e.g., two `transform` or two `moduleNameMapper` entries). JavaScript objects silently drop duplicate keys, causing test configuration to break.

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