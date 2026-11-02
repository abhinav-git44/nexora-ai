"""Module 9: subscriptions, usage metering, invoices. Stripe when configured; otherwise an explicitly labelled demo mode."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.audit import audit_ctx, track
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import OrgContext, require
from app.core.errors import bad_request, AppError
from app.core.plans import PLANS, PLAN_ORDER, get_subscription, usage_summary, effective_plan, current_usage, UNLIMITED
from app.models import Invoice, Membership
from app.modules.common import iso
from app.modules.notifications import notify

router = APIRouter(prefix="/api/billing", tags=["billing"])
settings = get_settings()


def billing_mode() -> str:
    return "stripe" if settings.stripe_secret_key else "demo"


def sub_out(db, org_id) -> dict:
    s = get_subscription(db, org_id)
    plan = effective_plan(db, org_id)
    return {"plan": s.plan, "plan_name": plan["name"], "status": s.status, "provider": s.provider, "trial_ends_at": iso(s.trial_ends_at),
            "current_period_end": iso(s.current_period_end), "cancel_at_period_end": s.cancel_at_period_end, "features": plan["features"],
            "limits": plan["limits"], "billing_mode": billing_mode()}


@router.get("/plans")
def plans():
    return {"plans": [{"key": k, **PLANS[k]} for k in PLAN_ORDER], "billing_mode": billing_mode(), "currency_options": ["usd", "inr"]}


@router.get("/subscription")
def subscription(ctx: OrgContext = Depends(require("billing.read")), db: Session = Depends(get_db)):
    return {**sub_out(db, ctx.org_id), "usage": usage_summary(db, ctx.org_id)}


@router.get("/usage")
def usage(ctx: OrgContext = Depends(require("org.read")), db: Session = Depends(get_db)):
    return usage_summary(db, ctx.org_id)


@router.get("/invoices")
def invoices(ctx: OrgContext = Depends(require("billing.read")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Invoice).where(Invoice.org_id == ctx.org_id).order_by(Invoice.created_at.desc())).all()
    return [{"id": str(i.id), "number": i.number, "amount": i.amount_cents / 100, "currency": i.currency, "status": i.status,
             "description": i.description, "period_start": iso(i.period_start), "period_end": iso(i.period_end), "hosted_url": i.hosted_url,
             "created_at": iso(i.created_at)} for i in rows]


class ChangePlanIn(BaseModel):
    plan: str
    currency: str = "usd"


@router.post("/change-plan")
def change_plan(body: ChangePlanIn, ctx: OrgContext = Depends(require("billing.manage")), db: Session = Depends(get_db)):
    if body.plan not in PLANS:
        raise bad_request("Unknown plan")
    if body.plan == "enterprise":
        raise bad_request("Enterprise plans are set up by our sales team. Contact sales from the pricing page.", "contact_sales")
    sub = get_subscription(db, ctx.org_id)
    old = sub.plan if sub.status != "trialing" else "free"
    # Downgrade guard: current usage must fit the target plan.
    target = PLANS[body.plan]["limits"]
    over = [m for m in ("documents", "agents", "workflows", "datasets", "members", "workspaces")
            if target.get(m, UNLIMITED) != UNLIMITED and current_usage(db, ctx.org_id, m) > target[m]]
    if over:
        raise bad_request(f"Reduce usage before downgrading: {', '.join(over)} exceed the {PLANS[body.plan]['name']} limits", "downgrade_blocked",
                          {"over": over})
    if billing_mode() == "stripe" and body.plan != "free":
        from app.billing_stripe import create_checkout
        return {"checkout_url": create_checkout(db, ctx, body.plan), "mode": "stripe"}
    now = datetime.now(timezone.utc)
    sub.plan, sub.status, sub.trial_ends_at = body.plan, "active", None
    sub.provider = "demo" if body.plan != "free" else "none"
    sub.current_period_start, sub.current_period_end = now, now + timedelta(days=30)
    price = PLANS[body.plan]["price_inr" if body.currency == "inr" else "price_usd"] or 0
    if price:
        n = db.scalar(select(func.count()).select_from(Invoice)) + 1
        db.add(Invoice(org_id=ctx.org_id, number=f"DEMO-{now:%Y%m}-{n:05d}", amount_cents=int(price * 100), currency=body.currency,
                       status="demo", description=f"{PLANS[body.plan]['name']} plan (demo billing — no payment taken)",
                       period_start=now, period_end=sub.current_period_end))
    direction = "upgraded" if PLAN_ORDER.index(body.plan) > PLAN_ORDER.index(old) else "downgraded"
    track(db, f"subscription_{direction}" if old != "free" or direction == "downgraded" else "subscription_started", org_id=ctx.org_id,
          user_id=ctx.user.id, properties={"from": old, "to": body.plan, "mode": "demo"})
    if direction == "upgraded" and old == "free":
        track(db, "subscription_upgraded", org_id=ctx.org_id, user_id=ctx.user.id, properties={"from": old, "to": body.plan, "mode": "demo"})
    audit_ctx(db, ctx, "billing.plan_changed", "subscription", sub.id, {"from": old, "to": body.plan, "mode": billing_mode()})
    for m in db.scalars(select(Membership).where(Membership.org_id == ctx.org_id, Membership.role.in_(["owner", "admin"]))):
        notify(db, ctx.org_id, m.user_id, "billing", f"Plan changed to {PLANS[body.plan]['name']}", link="/app/billing")
    return {**sub_out(db, ctx.org_id), "mode": "demo"}


@router.post("/cancel")
def cancel(ctx: OrgContext = Depends(require("billing.manage")), db: Session = Depends(get_db)):
    sub = get_subscription(db, ctx.org_id)
    if sub.plan == "free":
        raise bad_request("You are on the Free plan")
    sub.cancel_at_period_end = True
    audit_ctx(db, ctx, "billing.cancel_scheduled", "subscription", sub.id)
    track(db, "subscription_canceled", org_id=ctx.org_id, user_id=ctx.user.id, properties={"plan": sub.plan})
    return sub_out(db, ctx.org_id)


@router.post("/resume")
def resume(ctx: OrgContext = Depends(require("billing.manage")), db: Session = Depends(get_db)):
    sub = get_subscription(db, ctx.org_id)
    sub.cancel_at_period_end = False
    return sub_out(db, ctx.org_id)


@router.post("/portal")
def portal(ctx: OrgContext = Depends(require("billing.manage")), db: Session = Depends(get_db)):
    if billing_mode() != "stripe":
        raise AppError(501, "not_configured", "Payment provider not configured (demo billing mode)")
    from app.billing_stripe import portal_url
    return {"url": portal_url(db, ctx)}
