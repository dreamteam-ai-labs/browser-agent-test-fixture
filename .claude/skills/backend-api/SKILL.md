---
name: backend-api
description: Backend API development with FastAPI, Flask, database integration, and deployment
version: 1.0.0
triggers:
  - fastapi
  - flask
  - api
  - rest
  - graphql
  - backend
  - endpoint
  - database
  - orm
  - sqlalchemy
tags:
  - python
  - api
  - backend
  - database
  - rest
---

# Backend API Development

## Summary

Modern Python APIs should be:
- **Fast** - Async support for high concurrency
- **Type-safe** - Pydantic models for validation
- **Documented** - Auto-generated OpenAPI/Swagger
- **Testable** - Dependency injection, test clients
- **Secure** - Authentication, authorization, input validation

**Framework comparison:**
| Framework | Best For | Async | Auto Docs |
|-----------|----------|-------|-----------|
| FastAPI | Modern APIs, high performance | ✓ | ✓ |
| Flask | Simple APIs, flexibility | ✗ | ✗ |
| Django REST | Full-featured, batteries included | ✗ | ✓ |

**Project structure:**
```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py          # App factory
│   ├── config.py        # Settings
│   ├── models/          # Database models
│   ├── schemas/         # Pydantic schemas
│   ├── routers/         # API routes
│   ├── services/        # Business logic
│   ├── repositories/    # Data access
│   └── middleware/      # Custom middleware
├── tests/
├── alembic/             # Migrations
└── pyproject.toml
```

## Details

### FastAPI Basics

```python
from fastapi import FastAPI, HTTPException, Depends, Query
from pydantic import BaseModel, EmailStr
from typing import Annotated

app = FastAPI(title="My API", version="1.0.0")

# Pydantic schemas
class UserCreate(BaseModel):
    name: str
    email: EmailStr

class UserResponse(BaseModel):
    id: int
    name: str
    email: str

    class Config:
        from_attributes = True  # For ORM compatibility

# Routes
@app.get("/users", response_model=list[UserResponse])
async def list_users(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(le=100)] = 10,
):
    """List all users with pagination."""
    return await get_users(skip=skip, limit=limit)

@app.post("/users", response_model=UserResponse, status_code=201)
async def create_user(user: UserCreate):
    """Create a new user."""
    return await create_user_in_db(user)

@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int):
    """Get a user by ID."""
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

### Database with SQLAlchemy

**Models:**
```python
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship, DeclarativeBase
from datetime import datetime

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    posts = relationship("Post", back_populates="author")

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    content = Column(String)
    author_id = Column(Integer, ForeignKey("users.id"))

    author = relationship("User", back_populates="posts")
```

**Database session:**
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/db"

# Schema Creation (Required for multi-tenant setup)
async def create_schema():
    """Create dedicated schema using teamkey from n8n."""
    import asyncpg
    from urllib.parse import urlparse

    # Extract connection details from DATABASE_URL
    parsed = urlparse(DATABASE_URL)
    schema_name = "dt_test_fixture"  # teamkey from n8n (sanitized for PostgreSQL)

    # Create schema
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
        await conn.execute(f"SET search_path TO {schema_name}")
        print(f"✅ Schema '{schema_name}' created and activated")
    finally:
        await conn.close()

    # Update DATABASE_URL to use new schema
    return f"{DATABASE_URL}?options=-csearch_path%3D{schema_name}"

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

**Repository pattern:**
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(self, user: UserCreate) -> User:
        db_user = User(**user.model_dump())
        self.session.add(db_user)
        await self.session.flush()
        return db_user

    async def list(self, skip: int = 0, limit: int = 10) -> list[User]:
        result = await self.session.execute(
            select(User).offset(skip).limit(limit)
        )
        return list(result.scalars().all())
```

### Authentication

**JWT Authentication:**
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await UserRepository(db).get_by_id(user_id)
    if user is None:
        raise credentials_exception
    return user

@app.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_user)]
):
    return current_user
```

### Middleware and Error Handling

```python
from fastapi import Request
from fastapi.responses import JSONResponse
import time
import logging

logger = logging.getLogger(__name__)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
    response.headers["X-Process-Time"] = str(process_time)
    return response

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )
```

## Advanced

### Background Tasks

```python
from fastapi import BackgroundTasks

def send_email(email: str, message: str):
    # Simulate sending email
    time.sleep(5)
    print(f"Email sent to {email}")

@app.post("/send-notification")
async def send_notification(
    email: str,
    background_tasks: BackgroundTasks,
):
    background_tasks.add_task(send_email, email, "Hello!")
    return {"message": "Notification queued"}
```

### Caching with Redis

```python
import redis.asyncio as redis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache

@app.on_event("startup")
async def startup():
    redis_client = redis.from_url("redis://localhost")
    FastAPICache.init(RedisBackend(redis_client), prefix="api-cache")

@app.get("/expensive-operation")
@cache(expire=300)  # Cache for 5 minutes
async def expensive_operation():
    # Expensive computation
    return {"result": "cached"}
```

### Testing

**CRITICAL: Use both unit AND integration tests!**

See [testing-strategy](../testing-strategy/SKILL.md) for the full explanation.

**Unit tests (tests/unit/)** - Override dependencies for speed:
```python
import pytest
from httpx import AsyncClient
from app.main import app
from app.database import get_db

# Mock database for fast unit tests
@pytest.fixture
async def mock_db():
    """Injected mock database."""
    async with test_async_session() as session:
        yield session

@pytest.fixture
async def client(mock_db):
    """Client with mocked database dependency."""
    app.dependency_overrides[get_db] = lambda: mock_db
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_create_user(client: AsyncClient):
    response = await client.post(
        "/users",
        json={"name": "Test", "email": "test@example.com"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Test"
```

**Integration tests (tests/integration/)** - NO dependency overrides:
```python
# tests/integration/test_api_e2e.py
"""
Integration tests - real database, real endpoints, NO overrides.

These catch bugs that unit tests miss, like database initialization errors!
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base

# Real in-memory SQLite for integration tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

@pytest.fixture
def integration_client():
    """Client with REAL dependencies - no overrides!"""
    # Create real database tables
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as client:
        yield client
    Base.metadata.drop_all(bind=engine)

def test_user_registration_flow(integration_client):
    """
    Full user journey without mocked dependencies.

    This tests the REAL database initialization, connection pooling, etc.
    """
    # Register a user
    response = integration_client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "secret123"}
    )
    assert response.status_code == 201

    # Login with same credentials
    response = integration_client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "secret123"}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Access protected endpoint
    response = integration_client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"
```

**Why both?**
- Unit tests are fast and test logic in isolation
- Integration tests catch initialization bugs (database connections, config loading, etc.)

### Rate Limiting

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/limited")
@limiter.limit("5/minute")
async def limited_endpoint(request: Request):
    return {"message": "This endpoint is rate limited"}
```

## Resources

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [SQLAlchemy Docs](https://docs.sqlalchemy.org/)
- [Pydantic Docs](https://docs.pydantic.dev/)
- [Alembic (Migrations)](https://alembic.sqlalchemy.org/)
