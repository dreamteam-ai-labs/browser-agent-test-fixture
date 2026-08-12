---
name: project-fixture-overview
description: What browser-agent-test-fixture is and how its features.json top-level auth flags relate to its actual user-auth feature
metadata:
  type: project
---

browser-agent-test-fixture is a standalone fixture app (project management: users/projects/tasks) used to cheaply validate factory template and pipeline changes — not a real customer product. Expect it to be re-rendered from templates periodically (features re-reset to `pending`/`tests_pass:false` with header metadata added, but feature descriptions themselves stay stable across renders).

**Auth flag gotcha**: `features.json` top-level has `auth_required: false, auth_level: 0`. Despite this, the `user-auth` feature (phase 1) explicitly describes full JWT auth (bcrypt password hashing, POST /api/auth/register, POST /api/auth/login, GET /api/users/me, JWT middleware). The top-level `auth_required`/`auth_level` fields describe infra/service-to-service auth posture (Level 0 = no infra shared-secret auth needed), NOT whether the app has its own end-user auth.

**Why**: The architect role's fixed constraint list says "Auth: none — no end-user auth; do not plan auth flows" as a general default, but that default is overridden whenever a feature description explicitly specs out auth (as user-auth does here). Trust the feature descriptions over the blanket constraint header when they conflict.

**How to apply**: On this project, keep `constraints.auth: "jwt"` in architecture.json's fixture service, and keep the `users` entity (with register/login/me endpoints) extracted even though user-auth is a Phase 1 feature — projects.owner_id and tasks.assignee_id FK to it, so it must exist in the entity model regardless of the "skip phase 0/1" extraction rule.

The browser-agent existing service (see service-catalog.json) is not required by any feature (`required_services: []`) — it's used only by the qa-tester agent's browser smoke test, outside the app runtime. Its catalog entry has no `api_spec`, only url/description/health. Correct handling: include it as `source: "existing"` with `api_spec_source: "opt_out"` and a written rationale (QA-only tool, not integrated by any feature) rather than halting.
