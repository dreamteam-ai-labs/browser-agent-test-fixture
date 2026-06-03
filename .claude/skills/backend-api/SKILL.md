---
name: backend-api
description: Backend conventions for this project — FastAPI routers, SQLAlchemy models in models.py, /api prefix, response shapes, FK relationships.
when_to_use: Use when adding or editing backend endpoints, database models, Alembic migrations, request/response schemas, integration code for existing services, or debugging backend errors.
version: 1.0.0
triggers:
  - fastapi
  - api
  - backend
  - endpoint
  - database
tags:
  - python
  - api
  - backend
---

# Backend API Conventions

## Project Structure

```
src/fixture/
├── main.py          # FastAPI app + router registration
├── database.py      # Engine, session, schema management (Alembic-driven)
├── models.py        # SQLAlchemy ORM models + Pydantic schemas (canonical location for both)
├── auth.py          # GCP Identity Platform auth
├── config.py        # Pydantic settings
└── routers/         # One file per feature (e.g., routers/projects.py)
```

## Key Conventions

- **FastAPI** with Pydantic models for validation and auto-generated OpenAPI docs
- **SQLAlchemy 2.0** ORM with `DeclarativeBase` from `database.py`
- **Schema isolation**: All tables live in the project's dedicated PostgreSQL schema
- Every router MUST be registered in `main.py` via `app.include_router()`
- Use `from_attributes = True` on response models for ORM compatibility
- Pagination: `?page=1&page_size=10` returning `{items: [...], total: N, page: N}`
- Auth: `get_current_user()` dependency decodes JWT from `Authorization: Bearer` header

## Testing

- Unit tests in `tests/unit/` — mock dependencies for speed
- Integration tests in `tests/integration/` — real database, no mocks
- Run `pytest -v` before marking any feature complete
