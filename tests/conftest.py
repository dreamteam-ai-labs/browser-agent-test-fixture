"""Pytest configuration for browser-agent-test-fixture tests."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from fixture.database import Base, get_db
from fixture.main import app


TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_test_db():
    """Create test tables before each test and drop them after."""
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """Return a TestClient for the FastAPI app."""
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def auth_headers(client):
    """Register a test user and return Authorization headers."""
    resp = client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "TestPass123!",
        "name": "Test User",
    })
    assert resp.status_code == 200
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}
