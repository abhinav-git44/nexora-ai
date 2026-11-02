"""Module 12: platform administration (super admins only; hidden behind 404 for everyone else)."""
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text, or_
from sqlalchemy.orm import Session
from app.core.audit import audit
from app.core.db import get_db
from app.core.deps import require_super_admin, OrgContext, get_org_context
from app.core.errors import not_found, bad_request
from app.core.plans import PLANS, get_subscription, usage_summary
from app.models import (Organization, User, Membership, Subscription, AIRequest, Job, WorkflowExecution, Workflow, AuditLog, FeatureFlag,
                        SupportTicket, IntegrationConnection, AnalyticsEvent)
from app.modules.common import iso, user_brief

router = APIRouter(prefix="/api/admin", tags=["admin"])
support_router = APIRouter(prefix="/api/support", tags=["support"])
ROUTERS = [router, support_router]


@router.get("/overview")
def overview(admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    week = now - timedelta(days=7)
    subs = dict(db.execute(select(Subscription.plan, func.count()).group_by(Subscription.plan)).all())
    paid = db.execute(select(Subscription.plan, Subscription.provider, func.count()).where(Subscription.status == "active",
                                                                                        Subscription.plan.in_(["starter", "professional"]))
                      .group_by(Subscription.plan, Subscription.provider)).all()
    mrr_real = sum((PLANS[p]["price_usd"] or 0) * c for p, prov, c in paid if prov == "stripe")
    mrr_demo = sum((PLANS[p]["price_usd"] or 0) * c for p, prov, c in paid if prov != "stripe")
    ai = db.execute(select(func.count(), func.coalesce(func.sum(AIRequest.cost_usd), 0), func.count().filter(AIRequest.status == "error"),
                           func.coalesce(func.sum(AIRequest.input_tokens + AIRequest.output_tokens), 0)).where(AIRequest.created_at >= week)).one()
    jobs = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    last_job = db.scalar(select(func.max(Job.finished_at)))
    wf = dict(db.execute(select(WorkflowExecution.status, func.count()).where(WorkflowExecution.created_at >= week).group_by(WorkflowExecution.status)).all())
    db_ok = True
    try:
        db.execute(text("select 1"))
    except Exception:
        db_ok = False
    from app.core import ratelimit
    redis_ok = ratelimit._client() is not None
    from app.ai.gateway import provider_status
    return {
        "organizations": db.scalar(select(func.count()).select_from(Organization).where(Organization.deleted_at.is_(None))),
        "users": db.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None))),
        "active_users_7d": db.scalar(select(func.count(func.distinct(AnalyticsEvent.user_id))).where(AnalyticsEvent.created_at >= week)),
        "subscriptions_by_plan": subs,
        "mrr_usd": {"stripe_billed": mrr_real, "demo_billing": mrr_demo, "note": "Demo-billing subscriptions involve no real payments."},
        "ai_7d": {"requests": ai[0], "cost_usd": round(float(ai[1]), 4), "errors": ai[2], "tokens": int(ai[3]),
                  "error_rate": round(ai[2] / ai[0], 3) if ai[0] else 0},
        "jobs": jobs, "worker_last_completed_at": iso(last_job),
        "workflows_7d": wf,
        "health": {"database": db_ok, "redis": redis_ok, "ai_providers": provider_status(),
                   "worker": bool(last_job and last_job > now - timedelta(minutes=30)) or jobs.get("queued", 0) == 0},
        "integrations": dict(db.execute(select(IntegrationConnection.status, func.count()).group_by(IntegrationConnection.status)).all()),
    }


@router.get("/orgs")
def orgs(q: str | None = None, admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    query = select(Organization)
    if q:
        query = query.where(or_(Organization.name.ilike(f"%{q}%"), Organization.slug.ilike(f"%{q}%")))
    rows = db.scalars(query.order_by(Organization.created_at.desc()).limit(200)).all()
    members = dict(db.execute(select(Membership.org_id, func.count()).where(Membership.status == "active").group_by(Membership.org_id)).all())
    cost = dict(db.execute(select(AIRequest.org_id, func.sum(AIRequest.cost_usd)).group_by(AIRequest.org_id)).all())
    subs = {s.org_id: s for s in db.scalars(select(Subscription))}
    return [{"id": str(o.id), "name": o.name, "slug": o.slug, "created_at": iso(o.created_at), "suspended": o.is_suspended,
             "deleted": bool(o.deleted_at), "deletion_requested_at": iso(o.deletion_requested_at), "members": members.get(o.id, 0),
             "plan": subs[o.id].plan if o.id in subs else "free", "status": subs[o.id].status if o.id in subs else None,
             "ai_cost_usd": round(float(cost.get(o.id) or 0), 4)} for o in rows]


@router.get("/orgs/{org_id}")
def org_detail(org_id: uuid.UUID, admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    o = db.get(Organization, org_id)
    if not o:
        raise not_found("Organisation")
    ms = db.scalars(select(Membership).where(Membership.org_id == o.id)).all()
    sub = get_subscription(db, o.id)
    return {"id": str(o.id), "name": o.name, "suspended": o.is_suspended, "subscription": {"plan": sub.plan, "status": sub.status, "provider": sub.provider,
                                                                                         "custom_limits": sub.custom_limits},
            "usage": usage_summary(db, o.id), "members": [{"user": user_brief(m.user), "role": m.role, "status": m.status} for m in ms]}


class OrgAdminIn(BaseModel):
    suspended: bool | None = None
    plan: str | None = None
    custom_limits: dict[str, int] | None = None


@router.patch("/orgs/{org_id}")
def update_org(org_id: uuid.UUID, body: OrgAdminIn, admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    o = db.get(Organization, org_id)
    if not o:
        raise not_found("Organisation")
    sub = get_subscription(db, o.id)
    if body.suspended is not None:
        o.is_suspended = body.suspended
    if body.plan:
        if body.plan not in PLANS:
            raise bad_request("Unknown plan")
        sub.plan, sub.status, sub.trial_ends_at = body.plan, "active", None
        sub.provider = sub.provider if sub.provider == "stripe" else "manual"
    if body.custom_limits is not None:
        sub.custom_limits = body.custom_limits
    audit(db, "admin.org_updated", org_id=o.id, actor_id=admin.id, target_type="organization", target_id=o.id, details=body.model_dump(exclude_none=True))
    return {"ok": True}


@router.get("/users")
def users(q: str | None = None, admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    query = select(User).where(User.deleted_at.is_(None))
    if q:
        query = query.where(or_(User.email.ilike(f"%{q}%"), User.full_name.ilike(f"%{q}%")))
    rows = db.scalars(query.order_by(User.created_at.desc()).limit(200)).all()
    return [{"id": str(u.id), "email": u.email, "full_name": u.full_name, "is_active": u.is_active, "is_super_admin": u.is_super_admin,
             "email_verified": bool(u.email_verified_at), "created_at": iso(u.created_at), "last_login_at": iso(u.last_login_at)} for u in rows]


class UserAdminIn(BaseModel):
    is_active: bool


@router.patch("/users/{user_id}")
def update_user(user_id: uuid.UUID, body: UserAdminIn, admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise not_found("User")
    if u.id == admin.id:
        raise bad_request("You cannot deactivate yourself")
    u.is_active = body.is_active
    if not body.is_active:
        from app.models import UserSession
        for s in db.scalars(select(UserSession).where(UserSession.user_id == u.id, UserSession.revoked_at.is_(None))):
            s.revoked_at = datetime.now(timezone.utc)
    audit(db, "admin.user_updated", actor_id=admin.id, target_type="user", target_id=u.id, details={"is_active": body.is_active})
    return {"ok": True}


@router.get("/jobs")
def jobs(status: str = "failed", admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(Job).where(Job.status == status).order_by(Job.created_at.desc()).limit(100)).all()
    return [{"id": str(j.id), "kind": j.kind, "org_id": str(j.org_id) if j.org_id else None, "status": j.status, "attempts": j.attempts,
             "last_error": (j.last_error or "")[:1000], "created_at": iso(j.created_at), "finished_at": iso(j.finished_at)} for j in rows]


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: uuid.UUID, admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j or j.status != "failed":
        raise bad_request("Only failed jobs can be retried")
    j.status, j.attempts, j.run_after = "queued", 0, datetime.now(timezone.utc)
    audit(db, "admin.job_retried", actor_id=admin.id, target_type="job", target_id=j.id)
    return {"ok": True}


@router.get("/workflow-failures")
def workflow_failures(admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(WorkflowExecution, Workflow.name, Organization.name).join(Workflow, Workflow.id == WorkflowExecution.workflow_id)
                      .join(Organization, Organization.id == WorkflowExecution.org_id).where(WorkflowExecution.status == "failed")
                      .order_by(WorkflowExecution.created_at.desc()).limit(100)).all()
    return [{"id": str(e.id), "workflow": wn, "organization": on, "error": e.error, "created_at": iso(e.created_at)} for e, wn, on in rows]


@router.get("/ai-usage")
def ai_usage(days: int = 30, admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=min(days, 365))
    by_model = db.execute(select(AIRequest.provider, AIRequest.model, func.count(), func.sum(AIRequest.cost_usd), func.sum(AIRequest.input_tokens + AIRequest.output_tokens))
                          .where(AIRequest.created_at >= since).group_by(AIRequest.provider, AIRequest.model)).all()
    by_org = db.execute(select(Organization.name, func.count(), func.sum(AIRequest.cost_usd)).join(Organization, Organization.id == AIRequest.org_id)
                        .where(AIRequest.created_at >= since).group_by(Organization.name).order_by(func.sum(AIRequest.cost_usd).desc()).limit(20)).all()
    return {"by_model": [{"provider": p, "model": m, "requests": c, "cost_usd": round(float(s or 0), 4), "tokens": int(t or 0)} for p, m, c, s, t in by_model],
            "top_orgs": [{"organization": n, "requests": c, "cost_usd": round(float(s or 0), 4)} for n, c, s in by_org]}


@router.get("/audit-logs")
def audit_logs(action: str | None = None, admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action.startswith(action))
    rows = db.scalars(q.order_by(AuditLog.created_at.desc()).limit(300)).all()
    return [{"id": str(r.id), "org_id": str(r.org_id) if r.org_id else None, "actor_id": str(r.actor_id) if r.actor_id else None, "action": r.action,
             "target_type": r.target_type, "target_id": r.target_id, "details": r.details, "ip": r.ip, "created_at": iso(r.created_at)} for r in rows]


@router.get("/product-metrics")
def product_metrics(admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    """Acquisition/activation/retention from the event stream (same SQL as database/analytics_views.sql)."""
    weekly_signups = db.execute(text("""SELECT date_trunc('week', created_at)::date AS week, count(*) FROM analytics_events
                                       WHERE event = 'user_signed_up' GROUP BY 1 ORDER BY 1 DESC LIMIT 12""")).all()
    activation = db.execute(text("""
        WITH s AS (SELECT user_id, min(created_at) AS t0 FROM analytics_events WHERE event = 'user_signed_up' GROUP BY 1)
        SELECT count(*) AS signups,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM analytics_events e WHERE e.user_id = s.user_id AND e.event = 'ai_query_completed')) AS first_ai,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM analytics_events e WHERE e.user_id = s.user_id AND e.event = 'document_uploaded')) AS first_doc,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM analytics_events e WHERE e.user_id = s.user_id AND e.event = 'outcome_achieved')) AS first_outcome,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY (SELECT extract(epoch FROM min(e.created_at) - s.t0) / 60 FROM analytics_events e
                                                            WHERE e.user_id = s.user_id AND e.event = 'outcome_achieved')) AS median_ttfv_min
        FROM s""")).one()
    retention = db.execute(text("""
        WITH s AS (SELECT user_id, min(created_at) AS t0 FROM analytics_events WHERE event = 'user_signed_up' GROUP BY 1)
        SELECT count(*) FILTER (WHERE t0 < now() - interval '7 days') AS eligible_d7,
               count(*) FILTER (WHERE t0 < now() - interval '7 days' AND EXISTS (SELECT 1 FROM analytics_events e WHERE e.user_id = s.user_id
                                AND e.created_at >= s.t0 + interval '7 days' AND e.created_at < s.t0 + interval '14 days')) AS retained_d7,
               count(*) FILTER (WHERE t0 < now() - interval '30 days') AS eligible_d30,
               count(*) FILTER (WHERE t0 < now() - interval '30 days' AND EXISTS (SELECT 1 FROM analytics_events e WHERE e.user_id = s.user_id
                                AND e.created_at >= s.t0 + interval '30 days' AND e.created_at < s.t0 + interval '37 days')) AS retained_d30
        FROM s""")).one()
    nsm = db.execute(text("""SELECT date_trunc('week', created_at)::date, count(*) FROM analytics_events WHERE event = 'outcome_achieved'
                            GROUP BY 1 ORDER BY 1 DESC LIMIT 12""")).all()
    return {"weekly_signups": [{"week": w.isoformat(), "count": c} for w, c in weekly_signups],
            "activation": dict(activation._mapping), "retention": dict(retention._mapping),
            "north_star_weekly": [{"week": w.isoformat(), "outcomes": c} for w, c in nsm],
            "note": "Computed from recorded events only. With no real customers these figures reflect internal/test usage."}


class FlagIn(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_.-]{2,80}$")
    description: str = ""
    enabled: bool = False
    org_overrides: dict[str, bool] = {}


@router.get("/feature-flags")
def flags(admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    return [{"key": f.key, "description": f.description, "enabled": f.enabled, "org_overrides": f.org_overrides, "updated_at": iso(f.updated_at)}
            for f in db.scalars(select(FeatureFlag).order_by(FeatureFlag.key))]


@router.put("/feature-flags")
def upsert_flag(body: FlagIn, admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    f = db.get(FeatureFlag, body.key) or FeatureFlag(key=body.key)
    f.description, f.enabled, f.org_overrides = body.description, body.enabled, body.org_overrides
    db.merge(f)
    audit(db, "admin.feature_flag_updated", actor_id=admin.id, target_type="feature_flag", target_id=body.key, details=body.model_dump())
    return {"ok": True}


@router.get("/support-tickets")
def tickets(status: str | None = None, admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    q = select(SupportTicket, Organization.name).join(Organization, Organization.id == SupportTicket.org_id)
    if status:
        q = q.where(SupportTicket.status == status)
    rows = db.execute(q.order_by(SupportTicket.created_at.desc()).limit(200)).all()
    return [{"id": str(t.id), "organization": on, "subject": t.subject, "body": t.body, "status": t.status, "priority": t.priority,
             "admin_note": t.admin_note, "created_at": iso(t.created_at), "updated_at": iso(t.updated_at)} for t, on in rows]


class TicketAdminIn(BaseModel):
    status: str | None = None
    admin_note: str | None = None
    priority: str | None = None


@router.patch("/support-tickets/{tid}")
def update_ticket(tid: uuid.UUID, body: TicketAdminIn, admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    t = db.get(SupportTicket, tid)
    if not t:
        raise not_found("Ticket")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(t, k, v)
    if body.status == "resolved" and t.user_id:
        from app.modules.notifications import notify
        notify(db, t.org_id, t.user_id, "team", f"Support ticket resolved: {t.subject}", body.admin_note, link="/app/settings/support")
    return {"ok": True}


def flag_enabled(db: Session, key: str, org_id) -> bool:
    f = db.get(FeatureFlag, key)
    if not f:
        return False
    return bool(f.org_overrides.get(str(org_id), f.enabled))


@support_router.get("/flags")
def my_flags(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    return {f.key: bool(f.org_overrides.get(str(ctx.org_id), f.enabled)) for f in db.scalars(select(FeatureFlag))}


class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=5, max_length=10000)
    priority: str = "normal"


@support_router.get("/tickets")
def my_tickets(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    rows = db.scalars(select(SupportTicket).where(SupportTicket.org_id == ctx.org_id).order_by(SupportTicket.created_at.desc())).all()
    return [{"id": str(t.id), "subject": t.subject, "body": t.body, "status": t.status, "priority": t.priority, "admin_note": t.admin_note,
             "created_at": iso(t.created_at)} for t in rows]


@support_router.post("/tickets", status_code=201)
def create_ticket(body: TicketIn, ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    t = SupportTicket(org_id=ctx.org_id, user_id=ctx.user.id, subject=body.subject, body=body.body,
                      priority=body.priority if body.priority in ("low", "normal", "high", "urgent") else "normal")
    db.add(t)
    db.flush()
    return {"id": str(t.id), "status": t.status}
