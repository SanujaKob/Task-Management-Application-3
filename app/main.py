from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ----------------------
# App & Docs (with tags)
# ----------------------
tags_metadata = [
    {"name": "Health", "description": "Basic service health checks."},
    {"name": "Tasks", "description": "Core CRUD for tasks."},
    {"name": "Tasks: Convenience", "description": "Quick endpoints for status/progress/assignee updates."},
    {"name": "Tasks: Bulk", "description": "Bulk updates and deletions for tasks."},
    {"name": "Reminders", "description": "Create/list/delete reminders per task."},
    {"name": "Notifications", "description": "User notifications (stubbed in-memory)."},
]

app = FastAPI(
    title="ABACUS Task Manager API",
    version="0.1.0",
    openapi_tags=tags_metadata
)

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
# CRUD Endpoints  (Tasks)
# ----------------------

@app.get(f"{API_PREFIX}/tasks", response_model=List[TaskOut], tags=["Tasks"])
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


@app.post(f"{API_PREFIX}/tasks", response_model=TaskOut, status_code=201, tags=["Tasks"])
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


@app.get(f"{API_PREFIX}/tasks/{{task_id}}", response_model=TaskOut, tags=["Tasks"])
def get_task(task_id: UUID):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.put(f"{API_PREFIX}/tasks/{{task_id}}", response_model=TaskOut, tags=["Tasks"])
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


@app.patch(f"{API_PREFIX}/tasks/{{task_id}}", response_model=TaskOut, tags=["Tasks"])
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


@app.delete(f"{API_PREFIX}/tasks/{{task_id}}", status_code=204, tags=["Tasks"])
def delete_task(task_id: UUID):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    del TASKS[task_id]
    return None

# ----------------------
# Convenience Task Endpoints
# ----------------------

class StatusUpdate(BaseModel):
    status: Status


class ProgressUpdate(BaseModel):
    progress: int = Field(..., ge=0, le=100)


class AssigneeUpdate(BaseModel):
    assignee_id: Optional[UUID] = None


@app.patch(f"{API_PREFIX}/tasks/{{task_id}}/status", response_model=TaskOut, tags=["Tasks: Convenience"])
def set_status(task_id: UUID, payload: StatusUpdate):
    existing = TASKS.get(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    data = existing.model_dump()
    data["status"] = payload.status
    data["updated_at"] = _now()
    updated = TaskOut(**data)
    TASKS[task_id] = updated
    return updated


@app.patch(f"{API_PREFIX}/tasks/{{task_id}}/progress", response_model=TaskOut, tags=["Tasks: Convenience"])
def set_progress(task_id: UUID, payload: ProgressUpdate):
    existing = TASKS.get(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    data = existing.model_dump()
    data["progress"] = payload.progress
    data["updated_at"] = _now()
    updated = TaskOut(**data)
    TASKS[task_id] = updated
    return updated


@app.patch(f"{API_PREFIX}/tasks/{{task_id}}/assignee", response_model=TaskOut, tags=["Tasks: Convenience"])
def set_assignee(task_id: UUID, payload: AssigneeUpdate):
    existing = TASKS.get(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    data = existing.model_dump()
    data["assignee_id"] = payload.assignee_id
    data["updated_at"] = _now()
    updated = TaskOut(**data)
    TASKS[task_id] = updated
    return updated

# ----------------------
# Bulk Operations
# ----------------------

class BulkStatusUpdate(BaseModel):
    task_ids: List[UUID]
    status: Status


class BulkDelete(BaseModel):
    task_ids: List[UUID]


@app.post(f"{API_PREFIX}/tasks/bulk/status", response_model=List[TaskOut], tags=["Tasks: Bulk"])
def bulk_set_status(payload: BulkStatusUpdate):
    updated: List[TaskOut] = []
    for tid in payload.task_ids:
        if tid in TASKS:
            data = TASKS[tid].model_dump()
            data["status"] = payload.status
            data["updated_at"] = _now()
            updated_task = TaskOut(**data)
            TASKS[tid] = updated_task
            updated.append(updated_task)
    return updated


@app.post(f"{API_PREFIX}/tasks/bulk/delete", status_code=204, tags=["Tasks: Bulk"])
def bulk_delete(payload: BulkDelete):
    for tid in payload.task_ids:
        TASKS.pop(tid, None)
    return None

# ----------------------
# Reminders (per-task)
# ----------------------

class ReminderCreate(BaseModel):
    remind_at: datetime


class ReminderOut(BaseModel):
    id: UUID
    task_id: UUID
    remind_at: datetime
    created_at: datetime


REMINDERS: dict[UUID, ReminderOut] = {}


@app.post(f"{API_PREFIX}/tasks/{{task_id}}/reminders", response_model=ReminderOut, status_code=201, tags=["Reminders"])
def create_reminder(task_id: UUID, payload: ReminderCreate):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    rid = uuid4()
    reminder = ReminderOut(id=rid, task_id=task_id, remind_at=payload.remind_at, created_at=_now())
    REMINDERS[rid] = reminder
    return reminder


@app.get(f"{API_PREFIX}/tasks/{{task_id}}/reminders", response_model=List[ReminderOut], tags=["Reminders"])
def list_reminders(task_id: UUID):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    return [r for r in REMINDERS.values() if r.task_id == task_id]


@app.delete(f"{API_PREFIX}/tasks/{{task_id}}/reminders/{{reminder_id}}", status_code=204, tags=["Reminders"])
def delete_reminder(task_id: UUID, reminder_id: UUID):
    rem = REMINDERS.get(reminder_id)
    if not rem or rem.task_id != task_id:
        raise HTTPException(status_code=404, detail="Reminder not found")
    del REMINDERS[reminder_id]
    return None

# ----------------------
# Notifications (user-scoped stub)
# ----------------------

class NotificationType(str, Enum):
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_DUE_SOON = "TASK_DUE_SOON"
    TASK_OVERDUE = "TASK_OVERDUE"
    TASK_UPDATED = "TASK_UPDATED"


class NotificationOut(BaseModel):
    id: UUID
    type: NotificationType
    task_id: Optional[UUID] = None
    message: str
    is_read: bool = False
    created_at: datetime


NOTIFICATIONS: dict[UUID, NotificationOut] = {}


@app.get(f"{API_PREFIX}/notifications", response_model=List[NotificationOut], tags=["Notifications"])
def list_notifications(is_read: Optional[bool] = Query(None), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    items = list(NOTIFICATIONS.values())
    if is_read is not None:
        items = [n for n in items if n.is_read == is_read]
    return items[offset : offset + limit]


@app.patch(f"{API_PREFIX}/notifications/{{notification_id}}/read", response_model=NotificationOut, tags=["Notifications"])
def mark_notification_read(notification_id: UUID):
    n = NOTIFICATIONS.get(notification_id)
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True
    NOTIFICATIONS[notification_id] = n
    return n


@app.patch(f"{API_PREFIX}/notifications/read-all", status_code=204, tags=["Notifications"])
def mark_all_notifications_read():
    for k, v in list(NOTIFICATIONS.items()):
        v.is_read = True
        NOTIFICATIONS[k] = v
    return None


@app.delete(f"{API_PREFIX}/notifications/{{notification_id}}", status_code=204, tags=["Notifications"])
def delete_notification(notification_id: UUID):
    if notification_id not in NOTIFICATIONS:
        raise HTTPException(status_code=404, detail="Notification not found")
    del NOTIFICATIONS[notification_id]
    return None

# ----------------------
# Health
# ----------------------
@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
