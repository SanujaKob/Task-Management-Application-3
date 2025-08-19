from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import Enum
from typing import List, Optional, Dict
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from fastapi.security import HTTPBearer

# ----------------------
# App Setup with Tag Metadata
# ----------------------

tags_metadata = [
    {"name": "Auth", "description": "Register, login, and profile (DB-agnostic stubs)."},
    {"name": "Users", "description": "Admin-managed users and roles."},
    {"name": "Roles", "description": "Enumerate system roles."},
    {"name": "Teams", "description": "Teams/departments and membership management."},
    {"name": "Tasks", "description": "Core CRUD for tasks."},
    {"name": "Tasks: Convenience", "description": "Quick endpoints for status/progress/assignee."},
    {"name": "Tasks: Bulk", "description": "Bulk operations on tasks."},
    {"name": "Comments", "description": "Task comments (stub)."},
    {"name": "Attachments", "description": "Task attachments (metadata-only stub)."},
    {"name": "Reminders", "description": "Manage reminders per task."},
    {"name": "Notifications", "description": "User notifications (in-memory)."},
    {"name": "Dashboards: Manager", "description": "Team-level aggregates for managers."},
    {"name": "Dashboards: Admin", "description": "Global aggregates for admins."},
    {"name": "Simulation", "description": "Manual triggers for scheduler-like behaviors."},
    {"name": "Health", "description": "Simple health check endpoint."},
]

app = FastAPI(title="ABACUS Task Manager API", version="0.2.0", openapi_tags=tags_metadata)

# --- CORS (adjust for your frontend origin later) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/abascus/v1"

app = FastAPI(
    title="ABACUS Task Manager API",
    version="0.1.0",
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},  # optional, hides unused models
)

# Security scheme
security = HTTPBearer()

# Attach it in routes that need auth, e.g.
from fastapi import Depends, Security

@app.get(f"{API_PREFIX}/users", tags=["Users"])
def list_users(token: str = Security(security)):
    # In reality, you'd decode JWT or check token in DB
    if token.credentials != "dev-admin-token":
        raise HTTPException(status_code=401, detail="Invalid token")
    return list(USERS.values())

# ----------------------
# Security & Roles (stubs)
# ----------------------

class Role(str, Enum):
    admin = "admin"
    manager = "manager"
    user = "user"


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: Role = Role.user
    team_ids: List[UUID] = Field(default_factory=list)


class UserCreate(UserBase):
    password: str = Field(..., min_length=4)


class UserOut(UserBase):
    id: UUID
    created_at: datetime


USERS: Dict[UUID, UserOut] = {}
TOKENS: Dict[str, UUID] = {}  # access_token -> user_id


def _require_auth(Authorization: Optional[str] = Header(None)) -> UserOut:
    if not Authorization or not Authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = Authorization.split(" ", 1)[1]
    uid = TOKENS.get(token)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = USERS.get(uid)
    if not user:
        raise HTTPException(status_code=401, detail="User not found for token")
    return user


def _require_role(required: Role):
    def checker(current_user: UserOut = Depends(_require_auth)) -> UserOut:
        if current_user.role != required and current_user.role != Role.admin:
            raise HTTPException(status_code=403, detail=f"Requires role {required}")
        return current_user
    return checker


# ----------------------
# Auth Endpoints
# ----------------------

class RegisterIn(UserCreate):
    pass


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


@app.post(f"{API_PREFIX}/auth/register", response_model=UserOut, tags=["Auth"])
def register(payload: RegisterIn):
    # simplistic: no duplicate email checks for brevity
    uid = uuid4()
    user = UserOut(
        id=uid,
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        team_ids=payload.team_ids,
        created_at=datetime.utcnow(),
    )
    USERS[uid] = user
    return user


@app.post(f"{API_PREFIX}/auth/login", response_model=TokenOut, tags=["Auth"])
def login(payload: LoginIn):
    # demo: accept any password if email exists
    user = next((u for u in USERS.values() if u.email == payload.email), None)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = uuid4().hex
    TOKENS[token] = user.id
    return TokenOut(access_token=token)


@app.get(f"{API_PREFIX}/auth/me", response_model=UserOut, tags=["Auth"])
def me(current_user: UserOut = Depends(_require_auth)):
    return current_user


# ----------------------
# Users & Roles (Admin)
# ----------------------

@app.get(f"{API_PREFIX}/roles", response_model=List[str], tags=["Roles"])
def list_roles():
    return [r.value for r in Role]


@app.get(f"{API_PREFIX}/users", response_model=List[UserOut], tags=["Users"])
def list_users(role: Optional[Role] = None, search: Optional[str] = None, _: UserOut = Depends(_require_role(Role.admin))):
    items = list(USERS.values())
    if role:
        items = [u for u in items if u.role == role]
    if search:
        s = search.lower()
        items = [u for u in items if s in u.full_name.lower() or s in u.email.lower()]
    return items


@app.post(f"{API_PREFIX}/users", response_model=UserOut, status_code=201, tags=["Users"])
def create_user(payload: UserCreate, _: UserOut = Depends(_require_role(Role.admin))):
    uid = uuid4()
    user = UserOut(id=uid, email=payload.email, full_name=payload.full_name, role=payload.role, team_ids=payload.team_ids, created_at=datetime.utcnow())
    USERS[uid] = user
    return user


@app.get(f"{API_PREFIX}/users/{{user_id}}", response_model=UserOut, tags=["Users"])
def get_user(user_id: UUID, current: UserOut = Depends(_require_auth)):
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # allow admin or self
    if current.role != Role.admin and current.id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


@app.patch(f"{API_PREFIX}/users/{{user_id}}", response_model=UserOut, tags=["Users"])
def update_user(user_id: UUID, payload: UserCreate, _: UserOut = Depends(_require_role(Role.admin))):
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    updated = user.model_copy(update=dict(email=payload.email, full_name=payload.full_name, role=payload.role, team_ids=payload.team_ids))
    USERS[user_id] = updated
    return updated


@app.delete(f"{API_PREFIX}/users/{{user_id}}", status_code=204, tags=["Users"])
def delete_user(user_id: UUID, _: UserOut = Depends(_require_role(Role.admin))):
    if user_id not in USERS:
        raise HTTPException(status_code=404, detail="User not found")
    USERS.pop(user_id)
    return None


# ----------------------
# Teams
# ----------------------

class TeamBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    manager_ids: List[UUID] = Field(default_factory=list)


class TeamCreate(TeamBase):
    member_ids: List[UUID] = Field(default_factory=list)


class TeamOut(TeamBase):
    id: UUID
    member_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime


TEAMS: Dict[UUID, TeamOut] = {}


@app.get(f"{API_PREFIX}/teams", response_model=List[TeamOut], tags=["Teams"])
def list_teams(_: UserOut = Depends(_require_auth)):
    return list(TEAMS.values())


@app.post(f"{API_PREFIX}/teams", response_model=TeamOut, status_code=201, tags=["Teams"])
def create_team(payload: TeamCreate, _: UserOut = Depends(_require_role(Role.admin))):
    tid = uuid4()
    team = TeamOut(id=tid, name=payload.name, manager_ids=payload.manager_ids, member_ids=payload.member_ids, created_at=datetime.utcnow())
    TEAMS[tid] = team
    return team


@app.get(f"{API_PREFIX}/teams/{{team_id}}", response_model=TeamOut, tags=["Teams"])
def get_team(team_id: UUID, _: UserOut = Depends(_require_auth)):
    t = TEAMS.get(team_id)
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")
    return t


@app.patch(f"{API_PREFIX}/teams/{{team_id}}", response_model=TeamOut, tags=["Teams"])
def update_team(team_id: UUID, payload: TeamCreate, _: UserOut = Depends(_require_role(Role.admin))):
    t = TEAMS.get(team_id)
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")
    updated = t.model_copy(update=dict(name=payload.name, manager_ids=payload.manager_ids, member_ids=payload.member_ids))
    TEAMS[team_id] = updated
    return updated


@app.delete(f"{API_PREFIX}/teams/{{team_id}}", status_code=204, tags=["Teams"])
def delete_team(team_id: UUID, _: UserOut = Depends(_require_role(Role.admin))):
    if team_id not in TEAMS:
        raise HTTPException(status_code=404, detail="Team not found")
    TEAMS.pop(team_id)
    return None


@app.post(f"{API_PREFIX}/teams/{{team_id}}/members", response_model=TeamOut, tags=["Teams"])
def add_member(team_id: UUID, user_id: UUID, _: UserOut = Depends(_require_role(Role.manager))):
    t = TEAMS.get(team_id)
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")
    if user_id not in t.member_ids:
        t.member_ids.append(user_id)
        TEAMS[team_id] = t
    return t


@app.delete(f"{API_PREFIX}/teams/{{team_id}}/members/{{user_id}}", response_model=TeamOut, tags=["Teams"])
def remove_member(team_id: UUID, user_id: UUID, _: UserOut = Depends(_require_role(Role.manager))):
    t = TEAMS.get(team_id)
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")
    t.member_ids = [uid for uid in t.member_ids if uid != user_id]
    TEAMS[team_id] = t
    return t


# ----------------------
# Pydantic Schemas for Tasks
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
    team_id: Optional[UUID] = None


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
    team_id: Optional[UUID] = None


class TaskOut(TaskBase):
    id: UUID
    creator_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


# ----------------------
# In-memory stores for Tasks & others
# ----------------------

TASKS: Dict[UUID, TaskOut] = {}
REMINDERS: Dict[UUID, "ReminderOut"] = {}
NOTIFICATIONS: Dict[UUID, "NotificationOut"] = {}
COMMENTS: Dict[UUID, "CommentOut"] = {}
ATTACHMENTS: Dict[UUID, "AttachmentOut"] = {}


def _now() -> datetime:
    return datetime.utcnow()


# Seed sample data (optional)
admin_id = uuid4()
USERS[admin_id] = UserOut(id=admin_id, email="admin@example.com", full_name="Admin", role=Role.admin, team_ids=[], created_at=_now())
TOKENS["dev-admin-token"] = admin_id

seed_task_id = uuid4()
TASKS[seed_task_id] = TaskOut(
    id=seed_task_id,
    title="Kickoff meeting",
    description="Initial project kickoff with stakeholders",
    priority=Priority.high,
    status=Status.in_progress,
    progress=25,
    due_date=(date.today() + timedelta(days=1)),
    assignee_id=None,
    creator_id=admin_id,
    team_id=None,
    created_at=_now(),
    updated_at=_now(),
)


# ----------------------
# Utility: role-based task visibility
# ----------------------

def _visible_tasks_for(user: UserOut) -> List[TaskOut]:
    items = list(TASKS.values())
    if user.role == Role.admin:
        return items
    elif user.role == Role.manager:
        team_ids = [tid for tid, t in TEAMS.items() if user.id in t.manager_ids]
        return [t for t in items if t.team_id in team_ids or t.assignee_id == user.id or t.creator_id == user.id]
    else:
        return [t for t in items if t.assignee_id == user.id or t.creator_id == user.id]


# ----------------------
# CRUD Endpoints (Tasks)
# ----------------------

@app.get(f"{API_PREFIX}/tasks", response_model=List[TaskOut], tags=["Tasks"])
def list_tasks(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[Status] = Query(None),
    priority: Optional[Priority] = Query(None),
    assignee_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None, description="Search in title/description"),
    current_user: UserOut = Depends(_require_auth),
):
    """List tasks with filters, scoped by role/visibility."""
    items = _visible_tasks_for(current_user)
    if status is not None:
        items = [t for t in items if t.status == status]
    if priority is not None:
        items = [t for t in items if t.priority == priority]
    if assignee_id is not None:
        items = [t for t in items if t.assignee_id == assignee_id]
    if search:
        s = search.lower()
        items = [t for t in items if s in t.title.lower() or (t.description or "").lower().find(s) >= 0]
    return items[offset : offset + limit]


@app.post(f"{API_PREFIX}/tasks", response_model=TaskOut, status_code=201, tags=["Tasks"])
def create_task(payload: TaskCreate, current_user: UserOut = Depends(_require_auth)):
    """Create a new task. Emits TASK_ASSIGNED if assignee_id provided."""
    task_id = uuid4()
    now = _now()
    task = TaskOut(
        id=task_id,
        created_at=now,
        updated_at=now,
        creator_id=current_user.id,
        **payload.model_dump(),
    )
    TASKS[task_id] = task
    if task.assignee_id:
        _notify("TASK_ASSIGNED", task_id, f"You were assigned to: {task.title}", recipient_id=task.assignee_id)
    return task


@app.get(f"{API_PREFIX}/tasks/{{task_id}}", response_model=TaskOut, tags=["Tasks"])
def get_task(task_id: UUID, current_user: UserOut = Depends(_require_auth)):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task not in _visible_tasks_for(current_user):
        raise HTTPException(status_code=403, detail="Forbidden")
    return task


@app.put(f"{API_PREFIX}/tasks/{{task_id}}", response_model=TaskOut, tags=["Tasks"])
def replace_task(task_id: UUID, payload: TaskCreate, current_user: UserOut = Depends(_require_auth)):
    existing = TASKS.get(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    if existing.creator_id != current_user.id and current_user.role not in (Role.manager, Role.admin):
        raise HTTPException(status_code=403, detail="Forbidden")
    now = _now()
    updated = TaskOut(
        id=task_id,
        created_at=existing.created_at,
        updated_at=now,
        creator_id=existing.creator_id,
        **payload.model_dump(),
    )
    TASKS[task_id] = updated
    _notify("TASK_UPDATED", task_id, f"Task updated: {updated.title}")
    return updated


@app.patch(f"{API_PREFIX}/tasks/{{task_id}}", response_model=TaskOut, tags=["Tasks"])
def update_task(task_id: UUID, payload: TaskUpdate, current_user: UserOut = Depends(_require_auth)):
    existing = TASKS.get(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    if existing.creator_id != current_user.id and current_user.role not in (Role.manager, Role.admin):
        raise HTTPException(status_code=403, detail="Forbidden")
    data = existing.model_dump()
    for k, v in payload.model_dump(exclude_unset=True).items():
        data[k] = v
    data["updated_at"] = _now()
    updated = TaskOut(**data)
    TASKS[task_id] = updated
    _notify("TASK_UPDATED", task_id, f"Task updated: {updated.title}")
    return updated


@app.delete(f"{API_PREFIX}/tasks/{{task_id}}", status_code=204, tags=["Tasks"])
def delete_task(task_id: UUID, current_user: UserOut = Depends(_require_auth)):
    existing = TASKS.get(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    if existing.creator_id != current_user.id and current_user.role not in (Role.manager, Role.admin):
        raise HTTPException(status_code=403, detail="Forbidden")
    TASKS.pop(task_id)
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
def set_status(task_id: UUID, payload: StatusUpdate, _: UserOut = Depends(_require_auth)):
    existing = TASKS.get(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    data = existing.model_dump()
    data["status"] = payload.status
    data["updated_at"] = _now()
    updated = TaskOut(**data)
    TASKS[task_id] = updated
    _notify("TASK_UPDATED", task_id, f"Status changed to {payload.status}")
    return updated


@app.patch(f"{API_PREFIX}/tasks/{{task_id}}/progress", response_model=TaskOut, tags=["Tasks: Convenience"])
def set_progress(task_id: UUID, payload: ProgressUpdate, _: UserOut = Depends(_require_auth)):
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
def set_assignee(task_id: UUID, payload: AssigneeUpdate, _: UserOut = Depends(_require_auth)):
    existing = TASKS.get(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    data = existing.model_dump()
    data["assignee_id"] = payload.assignee_id
    data["updated_at"] = _now()
    updated = TaskOut(**data)
    TASKS[task_id] = updated
    if payload.assignee_id:
        _notify("TASK_ASSIGNED", task_id, f"You were assigned to: {updated.title}", recipient_id=payload.assignee_id)
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
def bulk_set_status(payload: BulkStatusUpdate, _: UserOut = Depends(_require_auth)):
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
def bulk_delete(payload: BulkDelete, _: UserOut = Depends(_require_auth)):
    for tid in payload.task_ids:
        TASKS.pop(tid, None)
    return None


# ----------------------
# Comments (per task)
# ----------------------

class CommentCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


class CommentOut(BaseModel):
    id: UUID
    task_id: UUID
    author_id: UUID
    text: str
    created_at: datetime


@app.post(f"{API_PREFIX}/tasks/{{task_id}}/comments", response_model=CommentOut, status_code=201, tags=["Comments"])
def create_comment(task_id: UUID, payload: CommentCreate, current: UserOut = Depends(_require_auth)):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    cid = uuid4()
    comment = CommentOut(id=cid, task_id=task_id, author_id=current.id, text=payload.text, created_at=_now())
    COMMENTS[cid] = comment
    return comment


@app.get(f"{API_PREFIX}/tasks/{{task_id}}/comments", response_model=List[CommentOut], tags=["Comments"])
def list_comments(task_id: UUID, _: UserOut = Depends(_require_auth)):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    return [c for c in COMMENTS.values() if c.task_id == task_id]


@app.delete(f"{API_PREFIX}/tasks/{{task_id}}/comments/{{comment_id}}", status_code=204, tags=["Comments"])
def delete_comment(task_id: UUID, comment_id: UUID, current: UserOut = Depends(_require_auth)):
    c = COMMENTS.get(comment_id)
    if not c or c.task_id != task_id:
        raise HTTPException(status_code=404, detail="Comment not found")
    if current.role not in (Role.manager, Role.admin) and current.id != c.author_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    COMMENTS.pop(comment_id)
    return None


# ----------------------
# Attachments (metadata-only stub)
# ----------------------

class AttachmentCreate(BaseModel):
    filename: str
    url: str  # in real app this would be UploadFile + storage


class AttachmentOut(BaseModel):
    id: UUID
    task_id: UUID
    filename: str
    url: str
    uploaded_at: datetime


@app.post(f"{API_PREFIX}/tasks/{{task_id}}/attachments", response_model=AttachmentOut, status_code=201, tags=["Attachments"])
def add_attachment(task_id: UUID, payload: AttachmentCreate, _: UserOut = Depends(_require_auth)):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    aid = uuid4()
    att = AttachmentOut(id=aid, task_id=task_id, filename=payload.filename, url=payload.url, uploaded_at=_now())
    ATTACHMENTS[aid] = att
    return att


@app.get(f"{API_PREFIX}/tasks/{{task_id}}/attachments", response_model=List[AttachmentOut], tags=["Attachments"])
def list_attachments(task_id: UUID, _: UserOut = Depends(_require_auth)):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    return [a for a in ATTACHMENTS.values() if a.task_id == task_id]


@app.delete(f"{API_PREFIX}/tasks/{{task_id}}/attachments/{{attachment_id}}", status_code=204, tags=["Attachments"])
def delete_attachment(task_id: UUID, attachment_id: UUID, _: UserOut = Depends(_require_auth)):
    a = ATTACHMENTS.get(attachment_id)
    if not a or a.task_id != task_id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    ATTACHMENTS.pop(attachment_id)
    return None


# ----------------------
# Reminders
# ----------------------

class ReminderCreate(BaseModel):
    remind_at: datetime


class ReminderOut(BaseModel):
    id: UUID
    task_id: UUID
    remind_at: datetime
    created_at: datetime


@app.post(f"{API_PREFIX}/tasks/{{task_id}}/reminders", response_model=ReminderOut, status_code=201, tags=["Reminders"])
def create_reminder(task_id: UUID, payload: ReminderCreate, _: UserOut = Depends(_require_auth)):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    rid = uuid4()
    reminder = ReminderOut(id=rid, task_id=task_id, remind_at=payload.remind_at, created_at=_now())
    REMINDERS[rid] = reminder
    return reminder


@app.get(f"{API_PREFIX}/tasks/{{task_id}}/reminders", response_model=List[ReminderOut], tags=["Reminders"])
def list_reminders(task_id: UUID, _: UserOut = Depends(_require_auth)):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    return [r for r in REMINDERS.values() if r.task_id == task_id]


@app.delete(f"{API_PREFIX}/tasks/{{task_id}}/reminders/{{reminder_id}}", status_code=204, tags=["Reminders"])
def delete_reminder(task_id: UUID, reminder_id: UUID, _: UserOut = Depends(_require_auth)):
    rem = REMINDERS.get(reminder_id)
    if not rem or rem.task_id != task_id:
        raise HTTPException(status_code=404, detail="Reminder not found")
    del REMINDERS[reminder_id]
    return None


# ----------------------
# Notifications (+ helpers)
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
    recipient_id: Optional[UUID] = None


NOTIFICATIONS: Dict[UUID, NotificationOut]


def _notify(ntype: str, task_id: UUID, message: str, recipient_id: Optional[UUID] = None):
    nid = uuid4()
    NOTIFICATIONS[nid] = NotificationOut(
        id=nid,
        type=NotificationType(ntype),
        task_id=task_id,
        message=message,
        is_read=False,
        created_at=_now(),
        recipient_id=recipient_id,
    )


@app.get(f"{API_PREFIX}/notifications", response_model=List[NotificationOut], tags=["Notifications"])
def list_notifications(is_read: Optional[bool] = Query(None), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), current: UserOut = Depends(_require_auth)):
    items = list(NOTIFICATIONS.values())
    # In a real app you’d filter by recipient. Here we show all for admins; otherwise only addressed or authored tasks.
    if current.role != Role.admin:
        items = [n for n in items if n.recipient_id in (None, current.id)]
    if is_read is not None:
        items = [n for n in items if n.is_read == is_read]
    return items[offset : offset + limit]


@app.patch(f"{API_PREFIX}/notifications/{{notification_id}}/read", response_model=NotificationOut, tags=["Notifications"])
def mark_notification_read(notification_id: UUID, current: UserOut = Depends(_require_auth)):
    n = NOTIFICATIONS.get(notification_id)
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    if current.role != Role.admin and n.recipient_id not in (None, current.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    n.is_read = True
    NOTIFICATIONS[notification_id] = n
    return n


@app.patch(f"{API_PREFIX}/notifications/read-all", status_code=204, tags=["Notifications"])
def mark_all_notifications_read(current: UserOut = Depends(_require_auth)):
    for k, v in list(NOTIFICATIONS.items()):
        if current.role == Role.admin or v.recipient_id in (None, current.id):
            v.is_read = True
            NOTIFICATIONS[k] = v
    return None


@app.delete(f"{API_PREFIX}/notifications/{{notification_id}}", status_code=204, tags=["Notifications"])
def delete_notification(notification_id: UUID, current: UserOut = Depends(_require_auth)):
    n = NOTIFICATIONS.get(notification_id)
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    if current.role != Role.admin and n.recipient_id not in (None, current.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    del NOTIFICATIONS[notification_id]
    return None


# ----------------------
# Dashboards
# ----------------------

@app.get(f"{API_PREFIX}/manager/overview", tags=["Dashboards: Manager"])
def manager_overview(current: UserOut = Depends(_require_role(Role.manager))):
    # Tasks visible to manager
    tasks = _visible_tasks_for(current)
    by_status: Dict[str, int] = {}
    overdue: List[TaskOut] = []
    due_soon: List[TaskOut] = []
    now = date.today()
    for t in tasks:
        by_status[t.status] = by_status.get(t.status, 0) + 1
        if t.due_date:
            if t.due_date < now:
                overdue.append(t)
            elif t.due_date <= now + timedelta(days=2):
                due_soon.append(t)
    return {
        "counts_by_status": by_status,
        "overdue": overdue,
        "due_soon": due_soon,
        "total": len(tasks),
    }


@app.get(f"{API_PREFIX}/admin/overview", tags=["Dashboards: Admin"])
def admin_overview(_: UserOut = Depends(_require_role(Role.admin))):
    tasks = list(TASKS.values())
    by_status: Dict[str, int] = {}
    now = date.today()
    overdue = [t for t in tasks if t.due_date and t.due_date < now]
    due_soon = [t for t in tasks if t.due_date and now <= t.due_date <= now + timedelta(days=2)]
    for t in tasks:
        by_status[t.status] = by_status.get(t.status, 0) + 1
    return {
        "counts_by_status": by_status,
        "overdue": overdue,
        "due_soon": due_soon,
        "total": len(tasks),
        "users": len(USERS),
        "teams": len(TEAMS),
    }


# ----------------------
# Simulation (manual scheduler trigger)
# ----------------------

@app.post(f"{API_PREFIX}/simulate/notifications/run", tags=["Simulation"], status_code=201)
def simulate_notifications(_: UserOut = Depends(_require_auth)):
    now = date.today()
    created = 0
    for t in TASKS.values():
        if not t.due_date:
            continue
        if t.due_date < now:
            _notify("TASK_OVERDUE", t.id, f"Task overdue: {t.title}", recipient_id=t.assignee_id)
            created += 1
        elif t.due_date == now or t.due_date == now + timedelta(days=1):
            _notify("TASK_DUE_SOON", t.id, f"Task due soon: {t.title}", recipient_id=t.assignee_id)
            created += 1
    return {"notifications_created": created}


# ----------------------
# Health
# ----------------------

@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
