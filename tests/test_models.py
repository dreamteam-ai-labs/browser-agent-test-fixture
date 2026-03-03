"""Tests for SQLAlchemy models and database schema."""
from fixture.models import User, Project, Task


def test_user_model_importable():
    assert User.__tablename__ == "users"
    assert hasattr(User, "email")
    assert hasattr(User, "hashed_password")
    assert hasattr(User, "display_name")


def test_project_model_importable():
    assert Project.__tablename__ == "projects"
    assert hasattr(Project, "name")
    assert hasattr(Project, "description")
    assert hasattr(Project, "user_id")


def test_task_model_importable():
    assert Task.__tablename__ == "tasks"
    assert hasattr(Task, "title")
    assert hasattr(Task, "status")
    assert hasattr(Task, "project_id")
    assert hasattr(Task, "user_id")
