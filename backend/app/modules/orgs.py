"""Organisations, members, invitations, workspaces, audit log, deletion workflow."""
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.audit import audit_ctx, track
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import OrgContext, get_current_user, get_org_context, require
from app.core.email import send_email
from app.core.errors import AppError, bad_request, forbidden, not_found
from app.core.permissions import ROLE_RANK, permissions_for
from app.core.plans import check_limit, require_feature, effective_plan, get_subscription
from app.core.security import new_token, sha256, verify_password
from app.models import Organization, Membership, Invitation, Workspace, User, AuditLog, ROLES
from app.modules.auth import create_org_for
from app.modules.common import iso, user_brief
from app.modules.notifications import notify

router = APIRouter(prefix="/api/orgs", tags=["organisations"])
settings = get_settings()


class OrgIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    industry: str | None = Field(default=None, max_length=100)
    size: str | None = Field(default=None, max_length=50)


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    industry: str | None = None
    size: str | None = None
    settings: dict | None = None


class InviteIn(BaseModel):
    email: EmailStr
    role: str = "member"


class RoleIn(BaseModel):
    role: str


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class DeleteOrgIn(BaseModel):
    confirm_name: str
    password: str


def org_out(o: Organization, ctx: OrgContext | None = None, db: Session | None = None) -> dict:
    d = {"id": str(o.id), "name": o.name, "slug": o.slug, "industry": o.industry, "size": o.size, "settings": o.settings or {},
         "created_at": iso(o.created_at), "deletion_requested_at": iso(o.deletion_requested_at)}
    if ctx:
        d["role"] = ctx.role
        d["permissions"] = permissions_for(ctx.role)
    if db is not None:
        plan = effective_plan(db, o.id)
        sub = get_subscription(db, o.id)
        d["plan"] = {"key": plan["key"], "name": plan["name"], "features": plan["features"], "status": sub.status,
                     "trial_ends_at": iso(sub.trial_ends_at)}
    return d


@router.get("")
def my_orgs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Membership).where(Membership.user_id == user.id, Membership.status == "active")).all()
    return [{**org_out(m.organization), "role": m.role} for m in rows if not m.organization.deleted_at]


@router.post("", status_code=201)
def create_org(body: OrgIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned = db.scalar(select(func.count()).select_from(Membership).where(Membership.user_id == user.id, Membership.role == "owner"))
    if owned >= 5 and not user.is_super_admin:
        raise bad_request("You can own at most 5 organisations", "org_limit")
    org = create_org_for(db, user, body.name.strip())
    org.industry, org.size = body.industry, body.size
    return {**org_out(org), "role": "owner"}


@router.get("/current")
def current_org(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    return org_out(ctx.org, ctx, db)


@router.patch("/current")
def update_org(body: OrgUpdate, ctx: OrgContext = Depends(require("org.update")), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    for k, v in data.items():
        setattr(ctx.org, k, v)
    audit_ctx(db, ctx, "org.updated", "organization", ctx.org_id, {"fields": list(data)})
    return org_out(ctx.org, ctx, db)


@router.post("/current/delete")
def request_org_deletion(body: DeleteOrgIn, ctx: OrgContext = Depends(require("org.delete")), db: Session = Depends(get_db)):
    """Two-step deletion: owner confirms name + password; org is locked and data is purged after a 7-day grace period."""
    if body.confirm_name != ctx.org.name or not verify_password(body.password, ctx.user.password_hash):
        raise bad_request("Organisation name or password did not match", "confirmation_required")
    ctx.org.deletion_requested_at = datetime.now(timezone.utc)
    from app.worker.queue import enqueue
    enqueue(db, "purge_org", {"org_id": str(ctx.org_id)}, org_id=ctx.org_id, delay_s=7 * 86400)
    audit_ctx(db, ctx, "org.deletion_requested", "organization", ctx.org_id)
    for m in db.scalars(select(Membership).where(Membership.org_id == ctx.org_id, Membership.role.in_(["owner", "admin"]))):
        send_email(db, m.user.email, f"{ctx.org.name} is scheduled for deletion",
                   f"{ctx.user.full_name} requested deletion of {ctx.org.name}. All data will be permanently removed in 7 days. "
                   f"An owner can cancel this from Settings → Organisation.", "org_deletion")
    return {"ok": True, "purge_after": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()}


@router.post("/current/delete/cancel")
def cancel_org_deletion(ctx: OrgContext = Depends(require("org.delete")), db: Session = Depends(get_db)):
    ctx.org.deletion_requested_at = None
    from app.models import Job
    for j in db.scalars(select(Job).where(Job.kind == "purge_org", Job.org_id == ctx.org_id, Job.status == "queued")):
        j.status, j.last_error = "failed", "cancelled by owner"
    audit_ctx(db, ctx, "org.deletion_cancelled", "organization", ctx.org_id)
    return {"ok": True}


# ---------------- members ----------------
@router.get("/current/members")
def list_members(ctx: OrgContext = Depends(require("members.read")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Membership).where(Membership.org_id == ctx.org_id).order_by(Membership.created_at)).all()
    return [{"id": str(m.id), "user": user_brief(m.user), "role": m.role, "status": m.status, "joined_at": iso(m.created_at),
             "last_login_at": iso(m.user.last_login_at)} for m in rows]


def _get_member(db, ctx, member_id) -> Membership:
    m = db.get(Membership, member_id)
    if not m or m.org_id != ctx.org_id:
        raise not_found("Member")
    return m


def _guard_target(ctx: OrgContext, m: Membership, new_role: str | None = None):
    # Admins cannot modify owners or grant roles above their own.
    if ROLE_RANK[m.role] > ROLE_RANK[ctx.role] or (new_role and ROLE_RANK[new_role] > ROLE_RANK[ctx.role]):
        raise forbidden("You cannot change a member with a higher role than yours")
    if m.user_id == ctx.user.id:
        raise bad_request("You cannot change your own membership here")


def _owners(db, org_id) -> int:
    return db.scalar(select(func.count()).select_from(Membership).where(Membership.org_id == org_id, Membership.role == "owner",
                                                                       Membership.status == "active"))


@router.patch("/current/members/{member_id}")
def change_role(member_id: uuid.UUID, body: RoleIn, ctx: OrgContext = Depends(require("members.manage")), db: Session = Depends(get_db)):
    if body.role not in ROLES:
        raise bad_request("Invalid role")
    m = _get_member(db, ctx, member_id)
    _guard_target(ctx, m, body.role)
    if m.role == "owner" and body.role != "owner" and _owners(db, ctx.org_id) <= 1:
        raise bad_request("An organisation must keep at least one owner")
    old, m.role = m.role, body.role
    audit_ctx(db, ctx, "member.role_changed", "membership", m.id, {"from": old, "to": body.role, "user": m.user.email})
    notify(db, ctx.org_id, m.user_id, "team", f"Your role in {ctx.org.name} is now {body.role}", link="/app/settings/members")
    return {"ok": True, "role": m.role}


@router.post("/current/members/{member_id}/deactivate")
def deactivate_member(member_id: uuid.UUID, ctx: OrgContext = Depends(require("members.manage")), db: Session = Depends(get_db)):
    m = _get_member(db, ctx, member_id)
    _guard_target(ctx, m)
    if m.role == "owner" and _owners(db, ctx.org_id) <= 1:
        raise bad_request("Cannot deactivate the last owner")
    m.status = "deactivated"
    audit_ctx(db, ctx, "member.deactivated", "membership", m.id, {"user": m.user.email})
    return {"ok": True}


@router.post("/current/members/{member_id}/reactivate")
def reactivate_member(member_id: uuid.UUID, ctx: OrgContext = Depends(require("members.manage")), db: Session = Depends(get_db)):
    m = _get_member(db, ctx, member_id)
    _guard_target(ctx, m)
    check_limit(db, ctx.org_id, "members")
    m.status = "active"
    audit_ctx(db, ctx, "member.reactivated", "membership", m.id, {"user": m.user.email})
    return {"ok": True}


@router.delete("/current/members/{member_id}")
def remove_member(member_id: uuid.UUID, ctx: OrgContext = Depends(require("members.manage")), db: Session = Depends(get_db)):
    m = _get_member(db, ctx, member_id)
    _guard_target(ctx, m)
    if m.role == "owner" and _owners(db, ctx.org_id) <= 1:
        raise bad_request("Cannot remove the last owner")
    audit_ctx(db, ctx, "member.removed", "membership", m.id, {"user": m.user.email})
    db.delete(m)
    return {"ok": True}


@router.post("/current/leave")
def leave_org(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    if ctx.role == "owner" and _owners(db, ctx.org_id) <= 1:
        raise bad_request("Transfer ownership before leaving")
    audit_ctx(db, ctx, "member.left", "membership", ctx.membership.id)
    db.delete(ctx.membership)
    return {"ok": True}


# ---------------- invitations ----------------
@router.get("/current/invitations")
def list_invitations(ctx: OrgContext = Depends(require("members.invite")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Invitation).where(Invitation.org_id == ctx.org_id, Invitation.accepted_at.is_(None),
                                               Invitation.revoked_at.is_(None)).order_by(Invitation.created_at.desc())).all()
    return [{"id": str(i.id), "email": i.email, "role": i.role, "expires_at": iso(i.expires_at), "created_at": iso(i.created_at),
             "expired": i.expires_at < datetime.now(timezone.utc)} for i in rows]


@router.post("/current/invitations", status_code=201)
def invite(body: InviteIn, ctx: OrgContext = Depends(require("members.invite")), db: Session = Depends(get_db)):
    if body.role not in ROLES or body.role == "owner" and ctx.role != "owner":
        raise bad_request("Invalid role for invitation")
    if ROLE_RANK[body.role] > ROLE_RANK[ctx.role]:
        raise forbidden("You cannot invite someone with a higher role than yours")
    if not ctx.user.email_verified_at:
        raise AppError(403, "email_unverified", "Verify your email address before inviting teammates")
    email = body.email.lower()
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user and db.scalar(select(Membership).where(Membership.org_id == ctx.org_id, Membership.user_id == existing_user.id)):
        raise AppError(409, "already_member", "This person is already a member")
    pending = db.scalar(select(func.count()).select_from(Invitation).where(Invitation.org_id == ctx.org_id, Invitation.accepted_at.is_(None),
                                                                          Invitation.revoked_at.is_(None)))
    check_limit(db, ctx.org_id, "members", increment=1 + pending)
    raw = new_token()
    inv = Invitation(org_id=ctx.org_id, email=email, role=body.role, token_hash=sha256(raw), invited_by=ctx.user.id,
                     expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    db.add(inv)
    db.flush()
    send_email(db, email, f"{ctx.user.full_name} invited you to {ctx.org.name} on NEXORA AI",
               f"You've been invited to join {ctx.org.name} as {body.role}.\n\nAccept: {settings.app_base_url}/invite?token={raw}\n\nExpires in 7 days.",
               "invitation")
    audit_ctx(db, ctx, "member.invited", "invitation", inv.id, {"email": email, "role": body.role})
    track(db, "member_invited", org_id=ctx.org_id, user_id=ctx.user.id, properties={"role": body.role})
    return {"id": str(inv.id), "email": email, "role": body.role, "expires_at": iso(inv.expires_at)}


@router.delete("/current/invitations/{inv_id}")
def revoke_invitation(inv_id: uuid.UUID, ctx: OrgContext = Depends(require("members.invite")), db: Session = Depends(get_db)):
    inv = db.get(Invitation, inv_id)
    if not inv or inv.org_id != ctx.org_id:
        raise not_found("Invitation")
    inv.revoked_at = datetime.now(timezone.utc)
    audit_ctx(db, ctx, "member.invitation_revoked", "invitation", inv.id, {"email": inv.email})
    return {"ok": True}


invitations_router = APIRouter(prefix="/api/invitations", tags=["organisations"])


class AcceptIn(BaseModel):
    token: str


@invitations_router.get("/lookup")
def lookup_invitation(token: str, db: Session = Depends(get_db)):
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == sha256(token)))
    if not inv or inv.accepted_at or inv.revoked_at or inv.expires_at < datetime.now(timezone.utc):
        raise bad_request("This invitation is invalid or has expired", "invalid_invitation")
    org = db.get(Organization, inv.org_id)
    return {"email": inv.email, "role": inv.role, "organization": org.name,
            "has_account": bool(db.scalar(select(User).where(User.email == inv.email)))}


@invitations_router.post("/accept")
def accept_invitation(body: AcceptIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == sha256(body.token)))
    if not inv or inv.accepted_at or inv.revoked_at or inv.expires_at < datetime.now(timezone.utc):
        raise bad_request("This invitation is invalid or has expired", "invalid_invitation")
    if inv.email != user.email:
        raise forbidden("This invitation was sent to a different email address")
    if not db.scalar(select(Membership).where(Membership.org_id == inv.org_id, Membership.user_id == user.id)):
        db.add(Membership(org_id=inv.org_id, user_id=user.id, role=inv.role))
    inv.accepted_at = datetime.now(timezone.utc)
    if not user.email_verified_at:
        user.email_verified_at = datetime.now(timezone.utc)
    track(db, "invitation_accepted", org_id=inv.org_id, user_id=user.id)
    if inv.invited_by:
        notify(db, inv.org_id, inv.invited_by, "team", f"{user.full_name} joined your organisation", link="/app/settings/members")
    return {"ok": True, "org_id": str(inv.org_id)}


# ---------------- workspaces ----------------
def ws_out(w: Workspace) -> dict:
    return {"id": str(w.id), "name": w.name, "description": w.description, "is_default": w.is_default, "created_at": iso(w.created_at)}


@router.get("/current/workspaces")
def list_workspaces(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    return [ws_out(w) for w in db.scalars(select(Workspace).where(Workspace.org_id == ctx.org_id).order_by(Workspace.created_at))]


@router.post("/current/workspaces", status_code=201)
def create_workspace(body: WorkspaceIn, ctx: OrgContext = Depends(require("workspaces.write")), db: Session = Depends(get_db)):
    check_limit(db, ctx.org_id, "workspaces")
    w = Workspace(org_id=ctx.org_id, name=body.name.strip(), description=body.description, created_by=ctx.user.id)
    db.add(w)
    db.flush()
    audit_ctx(db, ctx, "workspace.created", "workspace", w.id)
    track(db, "workspace_created", org_id=ctx.org_id, user_id=ctx.user.id)
    return ws_out(w)


@router.patch("/current/workspaces/{ws_id}")
def update_workspace(ws_id: uuid.UUID, body: WorkspaceIn, ctx: OrgContext = Depends(require("workspaces.write")), db: Session = Depends(get_db)):
    w = db.get(Workspace, ws_id)
    if not w or w.org_id != ctx.org_id:
        raise not_found("Workspace")
    w.name, w.description = body.name.strip(), body.description
    return ws_out(w)


@router.delete("/current/workspaces/{ws_id}")
def delete_workspace(ws_id: uuid.UUID, ctx: OrgContext = Depends(require("workspaces.write")), db: Session = Depends(get_db)):
    w = db.get(Workspace, ws_id)
    if not w or w.org_id != ctx.org_id:
        raise not_found("Workspace")
    if w.is_default:
        raise bad_request("The default workspace cannot be deleted")
    audit_ctx(db, ctx, "workspace.deleted", "workspace", w.id, {"name": w.name})
    db.delete(w)
    return {"ok": True}


# ---------------- audit log ----------------
@router.get("/current/audit-logs")
def audit_logs(limit: int = 100, action: str | None = None, ctx: OrgContext = Depends(require("audit.read")), db: Session = Depends(get_db)):
    require_feature(db, ctx.org_id, "audit_logs")
    q = select(AuditLog).where(AuditLog.org_id == ctx.org_id)
    if action:
        q = q.where(AuditLog.action.startswith(action))
    rows = db.scalars(q.order_by(AuditLog.created_at.desc()).limit(min(limit, 500))).all()
    actors = {u.id: u for u in db.scalars(select(User).where(User.id.in_({r.actor_id for r in rows if r.actor_id})))} if rows else {}
    return [{"id": str(r.id), "action": r.action, "actor": user_brief(actors.get(r.actor_id)), "target_type": r.target_type,
             "target_id": r.target_id, "details": r.details, "ip": r.ip, "created_at": iso(r.created_at)} for r in rows]
