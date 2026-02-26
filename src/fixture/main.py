import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import get_current_user, hash_password
from .database import Base, SessionLocal, engine
from .models import User
from .routers import auth, projects, tasks

SEED_EMAIL = "test@fixture.example.com"
SEED_PASSWORD = "TestFixture123!"
SEED_DISPLAY = "Test User"


def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == SEED_EMAIL).first():
            db.add(User(
                email=SEED_EMAIL,
                hashed_password=hash_password(SEED_PASSWORD),
                display_name=SEED_DISPLAY,
            ))
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Browser Agent Test Fixture", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(tasks.router)


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "browser-agent-test-fixture",
    }


# Also support /api/users/me (qa-smoke-test.py uses this path)
@app.get("/api/users/me")
def users_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email, "display_name": current_user.display_name}


@app.post("/api/admin/reset")
def admin_reset():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.add(User(
            email=SEED_EMAIL,
            hashed_password=hash_password(SEED_PASSWORD),
            display_name=SEED_DISPLAY,
        ))
        db.commit()
    finally:
        db.close()
    return {"ok": True, "seed_user": SEED_EMAIL}


# Mount static frontend (built Next.js export) — must be last
static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "out")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
