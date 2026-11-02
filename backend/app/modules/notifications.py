"""Module 11: in-app + email notifications with per-user preferences and read/unread state."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import OrgContext, get_org_context
from app.core.email import send_email
from app.models import Notification, NotificationPreference, User
from app.modules.common import iso

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
TYPES = ["task_assigned", "approval_request", "workflow_alert", "agent_alert", "document", "team", "billing", "mention"]
DEFAULT_PREFS = {t: {"in_app": True, "email": t in ("approval_request", "task_assigned", "workflow_alert", "billing")} for t in TYPES}


def get_prefs(db: Session, org_id, user_id) -> dict:
    p = db.get(NotificationPreference, (user_id, org_id))
    merged = {k: dict(v) for k, v in DEFAULT_PREFS.items()}
    if p:
        for k, v in (p.prefs or {}).items():
            if k in merged:
                merged[k].update(v)
    return merged


def notify(db: Session, org_id, user_id, type_: str, title: str, body: str | None = None, link: str | None = None):
    if user_id is None:
        return
    prefs = get_prefs(db, org_id, user_id).get(type_, {"in_app": True, "email": False})
    if prefs.get("in_app", True):
        db.add(Notification(org_id=org_id, user_id=user_id, type=type_, title=title[:300], body=body, link=link))
    if prefs.get("email"):
        u = db.get(User, user_id)
        if u and u.is_active:
            from app.core.config import get_settings
            send_email(db, u.email, title[:200], f"{body or title}\n\n{get_settings().app_base_url}{link or '/app'}", f"notify:{type_}")


@router.get("")
def list_notifications(unread_only: bool = False, limit: int = 50, ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    q = select(Notification).where(Notification.org_id == ctx.org_id, Notification.user_id == ctx.user.id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    rows = db.scalars(q.order_by(Notification.created_at.desc()).limit(min(limit, 200))).all()
    unread = db.scalar(select(func.count()).select_from(Notification).where(Notification.org_id == ctx.org_id, Notification.user_id == ctx.user.id,
                                                                           Notification.read_at.is_(None)))
    return {"unread": unread, "items": [{"id": str(n.id), "type": n.type, "title": n.title, "body": n.body, "link": n.link,
                                         "read": bool(n.read_at), "created_at": iso(n.created_at)} for n in rows]}


@router.post("/{nid}/read")
def mark_read(nid: uuid.UUID, ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.id == nid, Notification.user_id == ctx.user.id, Notification.org_id == ctx.org_id)
               .values(read_at=datetime.now(timezone.utc)))
    return {"ok": True}


@router.post("/{nid}/unread")
def mark_unread(nid: uuid.UUID, ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.id == nid, Notification.user_id == ctx.user.id, Notification.org_id == ctx.org_id)
               .values(read_at=None))
    return {"ok": True}


@router.post("/read-all")
def mark_all(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == ctx.user.id, Notification.org_id == ctx.org_id, Notification.read_at.is_(None))
               .values(read_at=datetime.now(timezone.utc)))
    return {"ok": True}


@router.get("/preferences")
def prefs(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    return get_prefs(db, ctx.org_id, ctx.user.id)


class PrefsIn(BaseModel):
    prefs: dict[str, dict[str, bool]]


@router.put("/preferences")
def set_prefs(body: PrefsIn, ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    clean = {k: {kk: bool(vv) for kk, vv in v.items() if kk in ("in_app", "email")} for k, v in body.prefs.items() if k in TYPES}
    p = db.get(NotificationPreference, (ctx.user.id, ctx.org_id))
    if p:
        p.prefs = clean
    else:
        db.add(NotificationPreference(user_id=ctx.user.id, org_id=ctx.org_id, prefs=clean))
    return get_prefs(db, ctx.org_id, ctx.user.id) | clean
