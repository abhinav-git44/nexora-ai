"""Module 7: tasks & projects."""
import uuid
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from app.core.audit import track, outcome
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import OrgContext, require
from app.core.errors import not_found, bad_request
from app.core.plans import check_limit, increment_usage
from app.core.storage import get_storage, make_key
from app.models import Task, TaskComment, TaskAttachment, TaskActivity, Membership, User
from app.modules.common import iso, user_brief
from app.modules.notifications import notify

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
STATUSES = ["todo", "in_progress", "in_review", "done"]
PRIORITIES = ["low", "medium", "high", "urgent"]


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20000)
    status: str = "todo"
    priority: str = "medium"
    assignee_id: str | None = None
    due_date: date | None = None
    labels: list[str] = []
    workspace_id: str | None = None
    source: str = "manual"


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    status: str | None = None
    priority: str | None = None
    assignee_id: str | None = None
    due_date: date | None = None
    labels: list[str] | None = None
    position: float | None = None
    clear_assignee: bool = False
    clear_due_date: bool = False


def task_out(t: Task, users: dict) -> dict:
    return {"id": str(t.id), "title": t.title, "description": t.description, "status": t.status, "priority": t.priority,
            "assignee": user_brief(users.get(t.assignee_id)), "assignee_id": str(t.assignee_id) if t.assignee_id else None,
            "due_date": t.due_date.isoformat() if t.due_date else None, "labels": t.labels, "source": t.source, "position": t.position,
            "created_by": user_brief(users.get(t.created_by)), "created_at": iso(t.created_at), "updated_at": iso(t.updated_at),
            "completed_at": iso(t.completed_at), "overdue": bool(t.due_date and t.due_date < date.today() and t.status != "done")}


def _users(db, ids) -> dict:
    ids = {i for i in ids if i}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}


def _member(db, org_id, uid: str | None):
    if not uid:
        return None
    u = uuid.UUID(uid)
    if not db.scalar(select(Membership).where(Membership.org_id == org_id, Membership.user_id == u, Membership.status == "active")):
        raise bad_request("Assignee must be an active member of this organisation")
    return u


def _activity(db, t: Task, user_id, action, details=None):
    db.add(TaskActivity(org_id=t.org_id, task_id=t.id, user_id=user_id, action=action, details=details or {}))


def get_task(db, ctx, task_id) -> Task:
    t = db.get(Task, task_id)
    if not t or t.org_id != ctx.org_id:
        raise not_found("Task")
    return t


@router.get("")
def list_tasks(status: str | None = None, assignee: str | None = None, label: str | None = None, q: str | None = None,
               due_from: date | None = None, due_to: date | None = None, ctx: OrgContext = Depends(require("tasks.read")), db: Session = Depends(get_db)):
    query = select(Task).where(Task.org_id == ctx.org_id)
    if status:
        query = query.where(Task.status == status)
    if assignee == "me":
        query = query.where(Task.assignee_id == ctx.user.id)
    elif assignee:
        query = query.where(Task.assignee_id == uuid.UUID(assignee))
    if q:
        query = query.where(or_(Task.title.ilike(f"%{q}%"), Task.description.ilike(f"%{q}%")))
    if due_from:
        query = query.where(Task.due_date >= due_from)
    if due_to:
        query = query.where(Task.due_date <= due_to)
    rows = db.scalars(query.order_by(Task.position, Task.created_at.desc()).limit(1000)).all()
    if label:
        rows = [t for t in rows if label in (t.labels or [])]
    users = _users(db, [t.assignee_id for t in rows] + [t.created_by for t in rows])
    return [task_out(t, users) for t in rows]


@router.get("/summary")
def summary(ctx: OrgContext = Depends(require("tasks.read")), db: Session = Depends(get_db)):
    by_status = dict(db.execute(select(Task.status, func.count()).where(Task.org_id == ctx.org_id).group_by(Task.status)).all())
    overdue = db.scalar(select(func.count()).select_from(Task).where(Task.org_id == ctx.org_id, Task.status != "done", Task.due_date < date.today()))
    mine = db.scalar(select(func.count()).select_from(Task).where(Task.org_id == ctx.org_id, Task.assignee_id == ctx.user.id, Task.status != "done"))
    return {"by_status": {s: by_status.get(s, 0) for s in STATUSES}, "overdue": overdue, "assigned_to_me": mine}


def create_task_record(db, ctx, body: TaskIn) -> Task:
    if body.status not in STATUSES or body.priority not in PRIORITIES:
        raise bad_request("Invalid status or priority")
    assignee = _member(db, ctx.org_id, body.assignee_id)
    maxpos = db.scalar(select(func.coalesce(func.max(Task.position), 0)).where(Task.org_id == ctx.org_id, Task.status == body.status)) or 0
    t = Task(org_id=ctx.org_id, title=body.title.strip(), description=body.description, status=body.status, priority=body.priority,
             assignee_id=assignee, due_date=body.due_date, labels=[l.strip()[:30] for l in body.labels if l.strip()][:10],
             created_by=ctx.user.id, source=body.source if body.source in ("manual", "ai") else "manual", position=maxpos + 1,
             workspace_id=uuid.UUID(body.workspace_id) if body.workspace_id else None)
    db.add(t)
    db.flush()
    _activity(db, t, ctx.user.id, "created")
    track(db, "task_created", org_id=ctx.org_id, user_id=ctx.user.id, properties={"source": t.source})
    if assignee and assignee != ctx.user.id:
        notify(db, ctx.org_id, assignee, "task_assigned", f"{ctx.user.full_name} assigned you: {t.title}", link=f"/app/tasks?task={t.id}")
    return t


@router.post("", status_code=201)
def create(body: TaskIn, ctx: OrgContext = Depends(require("tasks.write")), db: Session = Depends(get_db)):
    t = create_task_record(db, ctx, body)
    return task_out(t, _users(db, [t.assignee_id, t.created_by]))


@router.get("/{task_id}")
def get(task_id: uuid.UUID, ctx: OrgContext = Depends(require("tasks.read")), db: Session = Depends(get_db)):
    t = get_task(db, ctx, task_id)
    comments = db.scalars(select(TaskComment).where(TaskComment.task_id == t.id, TaskComment.org_id == ctx.org_id).order_by(TaskComment.created_at)).all()
    acts = db.scalars(select(TaskActivity).where(TaskActivity.task_id == t.id, TaskActivity.org_id == ctx.org_id).order_by(TaskActivity.created_at)).all()
    atts = db.scalars(select(TaskAttachment).where(TaskAttachment.task_id == t.id, TaskAttachment.org_id == ctx.org_id)).all()
    users = _users(db, [t.assignee_id, t.created_by] + [c.user_id for c in comments] + [a.user_id for a in acts])
    return {**task_out(t, users),
            "comments": [{"id": str(c.id), "user": user_brief(users.get(c.user_id)), "body": c.body, "created_at": iso(c.created_at)} for c in comments],
            "activity": [{"action": a.action, "user": user_brief(users.get(a.user_id)), "details": a.details, "created_at": iso(a.created_at)} for a in acts],
            "attachments": [{"id": str(a.id), "filename": a.filename, "size_bytes": a.size_bytes, "created_at": iso(a.created_at)} for a in atts]}


@router.patch("/{task_id}")
def update(task_id: uuid.UUID, body: TaskUpdate, ctx: OrgContext = Depends(require("tasks.write")), db: Session = Depends(get_db)):
    t = get_task(db, ctx, task_id)
    changes = {}
    if body.status and body.status != t.status:
        if body.status not in STATUSES:
            raise bad_request("Invalid status")
        changes["status"] = [t.status, body.status]
        t.status = body.status
        t.completed_at = datetime.now(timezone.utc) if body.status == "done" else None
        if body.status == "done":
            track(db, "task_completed", org_id=ctx.org_id, user_id=ctx.user.id, properties={"source": t.source})
            outcome(db, "task_completed", org_id=ctx.org_id, user_id=ctx.user.id, properties={"ai_generated": t.source != "manual"})
    if body.priority and body.priority != t.priority:
        if body.priority not in PRIORITIES:
            raise bad_request("Invalid priority")
        changes["priority"] = [t.priority, body.priority]
        t.priority = body.priority
    if body.clear_assignee:
        t.assignee_id = None
        changes["assignee"] = "cleared"
    elif body.assignee_id and body.assignee_id != (str(t.assignee_id) if t.assignee_id else None):
        t.assignee_id = _member(db, ctx.org_id, body.assignee_id)
        changes["assignee"] = body.assignee_id
        if t.assignee_id != ctx.user.id:
            notify(db, ctx.org_id, t.assignee_id, "task_assigned", f"{ctx.user.full_name} assigned you: {t.title}", link=f"/app/tasks?task={t.id}")
    if body.clear_due_date:
        t.due_date = None
    elif body.due_date:
        t.due_date = body.due_date
        changes["due_date"] = body.due_date.isoformat()
    for f in ("title", "description"):
        v = getattr(body, f)
        if v is not None and v != getattr(t, f):
            setattr(t, f, v)
            changes[f] = "updated"
    if body.labels is not None:
        t.labels = [l.strip()[:30] for l in body.labels if l.strip()][:10]
    if body.position is not None:
        t.position = body.position
    if changes:
        _activity(db, t, ctx.user.id, "updated", changes)
    return task_out(t, _users(db, [t.assignee_id, t.created_by]))


@router.delete("/{task_id}")
def delete(task_id: uuid.UUID, ctx: OrgContext = Depends(require("tasks.write")), db: Session = Depends(get_db)):
    t = get_task(db, ctx, task_id)
    if t.created_by != ctx.user.id and not ctx.can("agents.write"):
        raise bad_request("Only the creator or a manager can delete this task")
    db.delete(t)
    return {"ok": True}


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


@router.post("/{task_id}/comments", status_code=201)
def comment(task_id: uuid.UUID, body: CommentIn, ctx: OrgContext = Depends(require("tasks.write")), db: Session = Depends(get_db)):
    t = get_task(db, ctx, task_id)
    c = TaskComment(org_id=ctx.org_id, task_id=t.id, user_id=ctx.user.id, body=body.body)
    db.add(c)
    _activity(db, t, ctx.user.id, "commented")
    for uid in {t.assignee_id, t.created_by} - {ctx.user.id, None}:
        notify(db, ctx.org_id, uid, "mention", f"{ctx.user.full_name} commented on {t.title}", body.body[:200], link=f"/app/tasks?task={t.id}")
    db.flush()
    return {"id": str(c.id), "user": user_brief(ctx.user), "body": c.body, "created_at": iso(c.created_at)}


@router.post("/{task_id}/attachments", status_code=201)
async def attach(task_id: uuid.UUID, file: UploadFile = File(...), ctx: OrgContext = Depends(require("tasks.write")), db: Session = Depends(get_db)):
    t = get_task(db, ctx, task_id)
    max_b = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(max_b + 1)
    if len(data) > max_b or not data:
        raise bad_request("File is empty or too large")
    key = make_key(ctx.org_id, "task-attachments", file.filename or "file")
    get_storage().put(key, data)
    a = TaskAttachment(org_id=ctx.org_id, task_id=t.id, filename=(file.filename or "file")[:300], storage_key=key, size_bytes=len(data), uploaded_by=ctx.user.id)
    db.add(a)
    _activity(db, t, ctx.user.id, "attached", {"filename": a.filename})
    db.flush()
    return {"id": str(a.id), "filename": a.filename, "size_bytes": a.size_bytes}


@router.get("/{task_id}/attachments/{att_id}")
def download_attachment(task_id: uuid.UUID, att_id: uuid.UUID, ctx: OrgContext = Depends(require("tasks.read")), db: Session = Depends(get_db)):
    t = get_task(db, ctx, task_id)
    a = db.get(TaskAttachment, att_id)
    if not a or a.task_id != t.id or a.org_id != ctx.org_id:
        raise not_found("Attachment")
    return Response(get_storage().get(a.storage_key), media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{a.filename}"', "Content-Security-Policy": "sandbox"})


class ExtractIn(BaseModel):
    text: str = Field(min_length=10, max_length=50000)
    create: bool = False


@router.post("/ai/extract")
def ai_extract(body: ExtractIn, ctx: OrgContext = Depends(require("tasks.write")), db: Session = Depends(get_db)):
    """Convert meeting notes / conversations into tasks. With create=false returns suggestions for review (human in the loop)."""
    check_limit(db, ctx.org_id, "ai_messages")
    from app.modules.chat import extract_tasks_ai
    suggestions, meta = extract_tasks_ai(db, ctx.org_id, ctx.user.id, body.text)
    increment_usage(db, ctx.org_id, "ai_messages")
    members = {m.user.full_name.split()[0].lower(): m.user_id for m in db.scalars(select(Membership).where(
        Membership.org_id == ctx.org_id, Membership.status == "active")) if m.user.full_name}
    for s in suggestions:
        owner = (s.get("owner_name") or "").split(" ")[0].lower()
        s["assignee_id"] = str(members[owner]) if owner in members else None
    created = []
    if body.create:
        for s in suggestions:
            due = None
            try:
                due = date.fromisoformat(s["due_date"]) if s.get("due_date") else None
            except ValueError:
                pass
            t = create_task_record(db, ctx, TaskIn(title=s["title"], description=s.get("description", ""), priority=s.get("priority", "medium")
                                                   if s.get("priority") in PRIORITIES else "medium", due_date=due, assignee_id=s.get("assignee_id"),
                                                   labels=["ai-extracted"], source="ai"))
            created.append(str(t.id))
        track(db, "tasks_extracted_by_ai", org_id=ctx.org_id, user_id=ctx.user.id, properties={"count": len(created)})
        if created:
            outcome(db, "tasks_created_from_notes", org_id=ctx.org_id, user_id=ctx.user.id, properties={"count": len(created)})
    return {"suggestions": suggestions, "created_task_ids": created, "meta": meta}


@router.post("/ai/summary")
def ai_summary(ctx: OrgContext = Depends(require("tasks.read")), db: Session = Depends(get_db)):
    check_limit(db, ctx.org_id, "ai_messages")
    rows = db.scalars(select(Task).where(Task.org_id == ctx.org_id).order_by(Task.updated_at.desc()).limit(150)).all()
    users = _users(db, [t.assignee_id for t in rows])
    lines = [f"- [{t.status}] ({t.priority}) {t.title}" + (f" — due {t.due_date}" if t.due_date else "") +
             (f" — {users[t.assignee_id].full_name}" if t.assignee_id in users else " — unassigned") +
             (" — OVERDUE" if t.due_date and t.due_date < date.today() and t.status != "done" else "") for t in rows]
    from app.ai.gateway import generate
    from app.ai.providers.base import LLMRequest, ChatMessage
    text_ = "\n".join(lines) or "No tasks."
    r = generate(db, LLMRequest(messages=[ChatMessage(role="user", content=f"Today is {date.today()}. Tasks:\n{text_}\n\nWrite a status summary: progress, "
                                                         "overdue/at-risk items, unassigned urgent work, and 3 recommended next actions.")],
                                system="You are a project manager. Be specific and brief.", task_type="summarize",
                                metadata={"demo_handler": "summarize", "text": text_}), org_id=ctx.org_id, user_id=ctx.user.id, feature="tasks")
    increment_usage(db, ctx.org_id, "ai_messages")
    return {"summary": r.text, "model": r.model, "demo": r.demo}
