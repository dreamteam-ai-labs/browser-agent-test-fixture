---
name: testing-strategy
description: Testing pyramid pattern - unit vs integration tests to catch bugs that mocks hide
version: 1.0.0
triggers:
  - testing
  - unit test
  - integration test
  - tests pass but app fails
  - mocking
  - test strategy
  - pytest
tags:
  - python
  - testing
  - pytest
  - quality
---

# Testing Strategy: The Testing Pyramid

## Summary

**The Problem**: Unit tests with injected/mocked dependencies can hide bugs.

```python
# DANGEROUS PATTERN - tests pass but app fails!
@pytest.fixture
def store() -> TaskStore:
    store = TaskStore()
    set_store(store)  # Injects mock, BYPASSES get_store()
    return store

# The bug that slipped through:
def get_store():
    return TaskStore()  # BUG: Should be PersistentTaskStore()!
```

**The Solution**: Use a testing pyramid with BOTH unit AND integration tests:

```
tests/
├── conftest.py           # Shared fixtures
├── unit/                 # Fast, isolated, can mock
│   └── test_*.py
└── integration/          # Real code paths, NO mocks
    └── test_*.py
```

| Test Type | Purpose | Dependencies | Speed |
|-----------|---------|--------------|-------|
| **Unit** | Test functions in isolation | Mocked/injected | Fast |
| **Integration** | Test real code paths | Real | Slower |

**Rule**: If your test injects a dependency, you MUST have an integration test that doesn't.

## Details

### The Anti-Pattern Explained

When tests inject dependencies, they bypass initialization code:

```python
# src/cli.py
_store = None

def get_store():
    """Real initialization - THIS IS THE CODE PATH THAT MATTERS."""
    global _store
    if _store is None:
        _store = PersistentTaskStore("tasks.json")  # Or buggy: TaskStore()
    return _store

def set_store(store):
    """For testing - allows injecting a mock."""
    global _store
    _store = store
```

```python
# tests/test_cli.py - UNIT TESTS (can use injection)
@pytest.fixture
def store():
    store = TaskStore()  # In-memory, no file
    set_store(store)
    return store

def test_add_task(store):
    """Tests the add command with injected store."""
    # This test never calls get_store()!
    # If get_store() is broken, this test still passes!
    ...
```

### The Fix: Add Integration Tests

```python
# tests/integration/test_cli_e2e.py - INTEGRATION TESTS
"""Integration tests run real code paths without mocking."""

from typer.testing import CliRunner
from my_cli.cli import app

runner = CliRunner()

def test_tasks_persist_across_invocations(tmp_path, monkeypatch):
    """
    INTEGRATION TEST: Uses real file storage, no injected dependencies.

    This catches bugs in get_store() that unit tests miss!
    """
    # Use real file storage in temp directory
    monkeypatch.chdir(tmp_path)

    # First invocation - add a task
    result1 = runner.invoke(app, ["add", "Buy milk"])
    assert result1.exit_code == 0

    # Second invocation - task should persist
    result2 = runner.invoke(app, ["list"])
    assert result2.exit_code == 0
    assert "Buy milk" in result2.output  # Would FAIL if get_store() was broken!
```

### API Testing: Same Pattern

```python
# tests/unit/test_users.py - UNIT TESTS
@pytest.fixture
def mock_db():
    """Injected mock database."""
    return MockDatabase()

def test_create_user(mock_db):
    """Unit test with mocked database."""
    # Never tests real database initialization!
    ...
```

```python
# tests/integration/test_api_e2e.py - INTEGRATION TESTS
"""Integration tests use real database, real endpoints."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from src.main import app
from src.database import Base

# Real in-memory SQLite database
engine = create_engine("sqlite:///:memory:")

@pytest.fixture
def integration_client():
    """Client with REAL dependencies - no overrides!"""
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as client:
        yield client
    Base.metadata.drop_all(bind=engine)

def test_user_registration_flow(integration_client):
    """
    INTEGRATION TEST: Real database, real endpoints.

    This catches bugs in database initialization, connection pooling, etc.
    """
    # Register
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
    assert "access_token" in response.json()
```

### conftest.py Template

```python
"""
Test configuration for browser-agent-test-fixture.

TESTING PYRAMID STRUCTURE
=========================

This project uses a testing pyramid with two layers:

tests/unit/
    - Fast, isolated tests
    - CAN mock/inject dependencies for speed
    - Test individual functions and classes
    - Run frequently during development

tests/integration/
    - Test real code paths end-to-end
    - NO mocked dependencies
    - Test that initialization, storage, and APIs work correctly
    - Catch bugs that unit tests miss

CRITICAL: If a unit test injects a dependency (like set_store()),
         there MUST be an integration test that exercises the real path.

See: skills/testing-strategy/SKILL.md for full explanation.
"""

import pytest

# Shared fixtures go here
```

## Advanced

### Checklist: Does Your Test Catch Initialization Bugs?

For every feature, ask:

- [ ] Do I have unit tests for the core logic?
- [ ] Do I have integration tests that call the real entry points?
- [ ] If tests inject dependencies, do integration tests run WITHOUT injection?
- [ ] Do integration tests verify data persists across invocations?

### When to Use Each Test Type

| Scenario | Unit Test | Integration Test |
|----------|-----------|------------------|
| Pure function logic | Yes | Optional |
| Database operations | Mock for speed | Real DB required |
| CLI commands | CliRunner + mock store | CliRunner + real store |
| API endpoints | TestClient + mock deps | TestClient + real deps |
| File operations | Mock filesystem | Real temp files |

### Running Tests Separately

```bash
# Run only unit tests (fast)
pytest tests/unit/ -v

# Run only integration tests (slower, more thorough)
pytest tests/integration/ -v

# Run all tests
pytest -v
```

### CI Configuration

```yaml
# .github/workflows/test.yml
jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/unit/ -v --tb=short

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/integration/ -v --tb=short
```

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [Testing Pyramid by Martin Fowler](https://martinfowler.com/bliki/TestPyramid.html)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Typer Testing](https://typer.tiangolo.com/tutorial/testing/)
