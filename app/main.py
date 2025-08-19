from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="ABACUS Task Manager API", version="0.1.0")

# --- CORS (adjust for your frontend origin later) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

# ----------------------
# Pydantic Schemas (v2)
# ----------------------

class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Status(str, Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"
    blocked = "blocked"


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    priority: Priority = Priority.medium
    status: Status = Status.not_started
    progress: int = Field(0, ge=0, le=100)
    due_date: Optional[date] = None
    assignee_id: Optional[UUID] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    priority: Optional[Priority] = None
    status: Optional[Status] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    due_date: Optional[date] = None
    assignee_id: Optional[UUID] = None


class TaskOut(TaskBase):
    id: UUID
    creator_id: Optional[UUID] = None
    team_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


# ----------------------
# In-memory store (stub)
# ----------------------

TASKS: dict[UUID, TaskOut] = {}


def _now() -> datetime:
    return datetime.utcnow()


# Seed with a sample task (optional)
seed_id = uuid4()
TASKS[seed_id] = TaskOut(
    id=seed_id,
    title="Kickoff meeting",
    description="Initial project kickoff with stakeholders",
    priority=Priority.high,
    status=Status.in_progress,
    progress=25,
    due_date=None,
    assignee_id=None,
    creator_id=uuid4(),
    team_id=None,
    created_at=_now(),
    updated_at=_now(),
)


# ----------------------
# Utilities
# ----------------------

def _apply_filters(tasks: List[TaskOut],
                   status: Optional[Status],
                   priority: Optional[Priority],
                   assignee_id: Optional[UUID],
                   search: Optional[str]) -> List[TaskOut]:
    res = tasks
    if status is not None:
        res = [t for t in res if t.status == status]
    if priority is not None:
        res = [t for t in res if t.priority == priority]
    if assignee_id is not None:
        res = [t for t in res if t.assignee_id == assignee_id]
    if search:
        s = search.lower()
        res = [t for t in res if s in t.title.lower() or (t.description or "").lower().find(s) >= 0]
    return res


# ----------------------
# CRUD Endpoints
# ----------------------

@app.get(f"{API_PREFIX}/tasks", response_model=List[TaskOut])
def list_tasks(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[Status] = Query(None),
    priority: Optional[Priority] = Query(None),
    assignee_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None, description="Search in title/description"),
):
    """List tasks with basic filtering and pagination."""
    items = list(TASKS.values())
    items = _apply_filters(items, status, priority, assignee_id, search)
    return items[offset : offset + limit]


@app.post(f"{API_PREFIX}/tasks", response_model=TaskOut, status_code=201)
def create_task(payload: TaskCreate):
    """Create a new task."""
    task_id = uuid4()
    now = _now()
    task = TaskOut(
        id=task_id,
        created_at=now,
        updated_at=now,
        creator_id=uuid4(),  # placeholder; wire to auth user later
        team_id=None,
        **payload.model_dump(),
    )
    TASKS[task_id] = task
    return task


@app.get(f"{API_PREFIX}/tasks/{{task_id}}", response_model=TaskOut)
def get_task(task_id: UUID):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.put(f"{API_PREFIX}/tasks/{{task_id}}", response_model=TaskOut)
def replace_task(task_id: UUID, payload: TaskCreate):
    """Full update (PUT) – replaces all editable fields."""
    existing = TASKS.get(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    now = _now()
    updated = TaskOut(
        id=task_id,
        created_at=existing.created_at,
        updated_at=now,
        creator_id=existing.creator_id,
        team_id=existing.team_id,
        **payload.model_dump(),
    )
    TASKS[task_id] = updated
    return updated


@app.patch(f"{API_PREFIX}/tasks/{{task_id}}", response_model=TaskOut)
def update_task(task_id: UUID, payload: TaskUpdate):
    """Partial update (PATCH) – only fields provided are changed."""
    existing = TASKS.get(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    data = existing.model_dump()
    for k, v in payload.model_dump(exclude_unset=True).items():
        data[k] = v
    data["updated_at"] = _now()
    updated = TaskOut(**data)
    TASKS[task_id] = updated
    return updated


@app.delete(f"{API_PREFIX}/tasks/{{task_id}}", status_code=204)
def delete_task(task_id: UUID):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    del TASKS[task_id]
    return None


# Simple health check
@app.get("/health")
def health():
    return {"status": "ok"}
