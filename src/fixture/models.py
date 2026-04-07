from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=False, default="")
    created_at = Column(DateTime, server_default=func.now())

    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    assigned_tasks = relationship("Task", foreign_keys="Task.assignee_id", back_populates="assignee")
    owned_tasks = relationship("Task", foreign_keys="Task.user_id", back_populates="creator")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    owner = relationship("User", back_populates="projects")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    description = Column(String, default="")
    status = Column(String, default="pending")  # pending | in_progress | done
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # creator/owner
    url = Column(String, nullable=True)
    preview_url = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    project = relationship("Project", back_populates="tasks")
    assignee = relationship("User", foreign_keys=[assignee_id], back_populates="assigned_tasks")
    creator = relationship("User", foreign_keys=[user_id], back_populates="owned_tasks")
