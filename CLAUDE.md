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

1. **Phase 0 + Phase 1** (you, sequential): Complete ALL environment features, then build foundations — database schema/migrations, auth module, frontend project setup. Commit and push after each feature. IMPORTANT: The database-schema feature must define ALL tables needed by ALL features in the app (read the full features.json to identify every table). Later features should NOT need to create new tables — the schema should be complete from Phase 1.
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
- **CRUD pages required**: For every feature with CRUD operations, the frontend MUST have: a list page (`/[resource]`), a create page (`/[resource]/new`), and a detail/edit page (`/[resource]/[id]`). A feature is NOT complete until all its pages exist.

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

## Build-Time Feedback (`dreamteam-suggestions` MCP server)

This project also has access to `dreamteam-suggestions` — an MCP server registered in `.mcp.json` that exposes a single tool: `mcp__dreamteam-suggestions__suggest`. It's an append-only channel into the central DreamTeam suggestion-service, monitored by the operator. Agents post build-time observations the factory can act on (template gaps, prompt friction, missing scaffolds, false-positive QA, contract drift).

| Tool | Purpose |
|------|---------|
| `mcp__dreamteam-suggestions__suggest` | Submit a challenge, suggestion, or observation. Required: `agent_name`. Optional: `challenge`, `suggestion`, `category`, `raw` (JSONB). |

**When to call (general):** the moment something surprises you, blocks you, or reveals a gap that better tooling would have prevented. Per-agent triggers are listed in each agent's prompt — read them in `.claude/agents/<agent>.md`. Append-only; submissions can't be edited or deleted, so each entry stands alone. Routine task work is NOT signal — only friction, surprise, or actionable improvement ideas.

If you're reading this CLAUDE.md outside an agent context (e.g. during interactive `claude` use), the same tool is available — feel free to use it for ad-hoc operator-relevant observations.

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
- Follow PEP 8, use type hints, write docstrings for public APIs
- Keep functions focused and small

### Testing
- Write tests for all new features — run `pytest -v` before marking complete
- Integration test auth and API features against a running server, not just unit tests
- Frontend: `npm test` for component tests, `npm run build` to verify production build
- Do NOT hardcode `localhost:8000` in frontend API calls — it breaks when accessed remotely
- Do NOT define duplicate keys in jest.config.js — JavaScript silently drops them

### Committing
- Commit and push after each completed feature (`git add . && git commit -m "..." && git push`)
- Use descriptive messages: `feat: implement user authentication`
- Update `claude-progress.txt` before committing

### Hook Trust Model

The `.claude/hooks/` gates (path-guard, package-guard, build-gate, commit-guard,
dep-guard, alembic-guard, contract-check, skip-test-check, etc.) enforce
**agent honesty, not adversarial defense**. They exist so honest agents
don't take shortcuts — forgetting to declare deps, skipping tests, drifting
from contracts, writing to the wrong package, etc. They are forcing
functions, not security boundaries.

What this means concretely:

- Agent-self-attested state (`set_state(key='last_test_result', value='pass')`,
  `set_state(key='build_phase', value='builders')`) is trusted. Gates that
  read these don't independently verify them. A misbehaving agent could
  lie; the gate is for honest forgetfulness.
- Most hooks fail-open on parse errors (corrupt stdin, malformed event JSON)
  so hook bugs never kill agents. Logged in `.claude/hooks/hook-log.txt` for
  audit.
- `protect-harness-paths.py` is the ONE adversarial-grade gate — it blocks
  agent writes to `.claude/`, `.git/`, `.vscode/`, and shell-config files
  unconditionally (escape hatch: `DREAMTEAM_ALLOW_HARNESS_MUTATION=1`).
  Defends against the CC 2.1.126 `--dangerously-skip-permissions` scope
  broadening. Runs first in the PreToolUse chain.
- Lead session (the orchestrator running this CLAUDE.md) is unrestricted
  by `path-guard.py` — match_agent("") returns None → allow-everything.
  Intentional: lead is operator-supervised, not a delegated teammate.
  Harness-path protection still applies via protect-harness-paths.

If you find yourself wanting to "work around" a gate, that's the signal
the gate is doing its job — pause + understand why it fired. Don't reach
for the escape hatch unless the operator has authorized it for the
specific case.

### Outbound Egress Policy

Network calls to external hosts are gated against a hostname allowlist at
`.claude/egress-allowlist.json`. Two enforcement layers run in parallel:

1. **Bash level** — `outbound-egress-guard.py` (PreToolUse on Bash). Parses
   URLs from the command + checks each host. Catches curl, wget (also
   explicitly denied in `settings.json`), git clone over https, pip
   `--index-url`, npm `--registry`, and any other URL-bearing flag.
2. **Python level** — `.claude/scripts/sitecustomize.py` (auto-imported
   on every Python interpreter start via PYTHONPATH). Monkey-patches
   `urllib.request.urlopen`, `http.client.HTTPConnection.request`, and
   `socket.create_connection` to check the destination host before
   connecting. Raises `EgressBlockedError` on unlisted host. Covers
   httpx, requests, anthropic SDK, openai SDK, stripe SDK, etc. — anything
   that goes through Python's network stack.

The Bash and Python layers share the same allowlist file. Editing the
JSON file is operator-only (protected by `protect-harness-paths.py`).

Default allowlist covers: localhost, PyPI, npm, GitHub, Anthropic API +
docs, OpenAI, Stripe, Google APIs, Cloudflare, Coolify. Hosts match by
suffix — `github.com` allows `api.github.com`, `raw.github.com`, etc.

**If you need to reach an unlisted host mid-build:**
- Set `DREAMTEAM_ALLOW_UNLISTED_EGRESS=1` for the specific call. This
  matches the override pattern used by other gates. Logged to
  `hook-log.txt` as `ALLOW_VIA_ESCAPE` for the audit trail.
- OR ask the operator to add the host to the allowlist. The escape env
  var is for one-off cases; the allowlist is the right home for durable
  permits.

---

## Commands

Custom slash commands are in `.claude/commands/`:
- `/status` - Check feature progress

---

## Dependencies

- `reliable-ai` - Core agent patterns and utilities
- See `pyproject.toml` for full list

---

## Known Deployment Pitfalls

These are real bugs from previous production builds. Each one caused a deployment failure.

### Database
- **Define ALL tables in the database-schema feature.** Later features must NOT create new tables. Read the full `features.json` to identify every table before starting database-schema. If a feature needs a table that doesn't exist, the Coolify deploy will fail with `UndefinedTable`.
- **ORM models must match the schema exactly.** If a model has `hashed_password` but the table has `password`, the app crashes on startup. Test every model with real CRUD operations, not just `create_all()`.
- **CASCADE relationships:** If a category has budgets, `DELETE /categories/{id}` will fail unless the relationship has `cascade="all, delete-orphan"`. Test delete operations for every resource that has foreign keys.

### Frontend
- **All API calls use relative URLs (`/api/...`).** The `next.config.mjs` rewrites proxy handles routing to the backend. Do NOT hardcode `localhost:8000` or any absolute URL in frontend code.
- **Tailwind content paths:** Use `./src/**/*.{js,ts,jsx,tsx}` in `tailwind.config.ts`, NOT `./app/**/*`. The App Router puts files in `src/app/`, not `app/`.
- **Every CRUD feature needs frontend pages:** list page (`/[resource]`), create page (`/[resource]/new`), detail/edit page (`/[resource]/[id]`). Missing pages are flagged as critical by QA.
- **`npm run build` must pass.** Run it before marking frontend features complete. Build errors break Coolify deployment.

### Package & Dependencies
- **All code MUST be in `src/fixture/`.** Do NOT create additional packages in `src/`. The Dockerfile and start.sh are hardcoded to `fixture`. A second package will not be installed in the Docker image.
- **All imports must be declared in `pyproject.toml`.** If you `import requests`, add `requests` to `[project.dependencies]`. Undeclared deps pass in the codespace (installed globally) but fail in the Docker clean install.

### Testing
- `pytest` is at `/usr/local/py-utils/bin/pytest` in codespaces — use that path if `pytest` is not on PATH
- When running `next dev`, ensure NODE_ENV is NOT set to "production" (breaks Tailwind PostCSS). Use `env -u NODE_ENV npx next dev -p 3000`
- When creating `frontend/tsconfig.json`, exclude `__tests__` from compilation
- Verify signup/login via real HTTP requests — unit tests alone miss auth integration bugs

### Post-deploy QA user seed
- The QA user created by `scripts/qa-smoke-test.py` lives in the codespace's local database only — it does NOT travel to the deployed container.
- The orchestrator is expected to run `python scripts/seed-qa-user.py --url <deployed-url>` after `/api/health` returns 200. The script is idempotent (409 = already exists = success).
- If the seed step did not run and you can't log in on the deployed app, either invoke the script manually or use the app's signup flow.