import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Task, User

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

BROWSER_AGENT_URL = os.environ.get("BROWSER_AGENT_URL", "https://browser.dreamteamlabs.co.uk")


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    project_id: Optional[int] = None
    assignee_id: Optional[int] = None
    status: str = "pending"
    url: Optional[str] = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    status: str
    project_id: Optional[int]
    assignee_id: Optional[int]
    user_id: int
    url: Optional[str]
    preview_url: Optional[str]


@router.get("", response_model=list[TaskResponse])
def list_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Task).filter(Task.user_id == user.id).all()


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = Task(
        title=body.title,
        description=body.description,
        project_id=body.project_id,
        assignee_id=body.assignee_id,
        status=body.status,
        user_id=user.id,
        url=body.url,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, body: TaskCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    task.title = body.title
    task.description = body.description
    task.project_id = body.project_id
    task.assignee_id = body.assignee_id
    task.status = body.status
    task.url = body.url
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    db.delete(task)
    db.commit()


@router.post("/{task_id}/preview", response_model=dict)
def capture_preview(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if not task.url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task has no URL set")

    try:
        resp = httpx.post(
            f"{BROWSER_AGENT_URL}/diagnose",
            json={"url": task.url},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Browser agent error: {e}")

    screenshot_url = data.get("screenshotUrl")
    if not screenshot_url:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Browser agent returned no screenshot")

    task.preview_url = screenshot_url
    db.commit()
    db.refresh(task)
    return {"preview_url": task.preview_url}
