# QA Browser Test Harness

This is an isolated harness to prove the QA browser smoke test works end-to-end.

## What This Is

A working app (FastAPI + Next.js 14) with auth, projects, and tasks. All 5 features are already built and working. Your ONLY job is to run the QA tester agent and verify the browser smoke test passes.

## What To Do

1. Spawn the QA tester agent: `@qa-tester`
2. The QA tester will:
   - Start backend and frontend
   - Test all API endpoints
   - Run `scripts/qa-smoke-test.py` (registers user, tests auth, calls browser agent)
   - Write results to `qa-report.json`
3. Review the QA report and fix any issues found

## App Structure

- **Backend**: `src/fixture/main.py` — FastAPI on port 8000
  - `POST /api/auth/register` — register user (email, password, display_name)
  - `POST /api/auth/login` — login, returns `{ token: "..." }`
  - `GET /api/users/me` — verify token (Bearer auth)
  - `GET /api/projects` — list projects (auth required)
  - `POST /api/projects` — create project (auth required)
  - `GET /api/tasks` — list tasks (auth required)
  - `POST /api/tasks` — create task (auth required)
  - `GET /api/health` — health check
  - `POST /api/admin/reset` — reset DB and re-seed
- **Frontend**: `frontend/` — Next.js 14 on port 3000
  - `/login` — login form
  - `/register` — registration form
  - `/dashboard` — welcome + counts
  - `/projects` — project list + create
  - `/tasks` — task list + create
- **Database**: SQLite (`fixture.db`)
- **Seed user**: `test@fixture.example.com` / `TestFixture123!`

## Rules

- Do NOT modify any source code unless the QA tester finds actual bugs
- The browser agent is at `https://claude-browser-agent.onrender.com`
- Screenshots should be uploaded (`uploadScreenshots: true` in qa-smoke-test.py)
