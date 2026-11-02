"""Stripe adapter (REST via httpx; no card data ever touches NEXORA servers — Checkout/Portal are Stripe-hosted)."""
from datetime import datetime, timezone
import httpx
from app.core.config import get_settings
from app.core.plans import get_subscription
from app.models import Invoice

API = "https://api.stripe.com/v1"


def _post(path: str, data: dict) -> dict:
    s = get_settings()
    r = httpx.post(f"{API}{path}", data=data, auth=(s.stripe_secret_key, ""), timeout=15)
    r.raise_for_status()
    return r.json()


def create_checkout(db, ctx, plan: str) -> str:
    s = get_settings()
    price = {"starter": s.stripe_price_starter, "professional": s.stripe_price_professional}.get(plan)
    if not price:
        raise RuntimeError(f"STRIPE_PRICE_{plan.upper()} is not configured")
    sub = get_subscription(db, ctx.org_id)
    if not sub.provider_customer_id:
        cust = _post("/customers", {"email": ctx.user.email, "name": ctx.org.name, "metadata[org_id]": str(ctx.org_id)})
        sub.provider_customer_id = cust["id"]
    sess = _post("/checkout/sessions", {"mode": "subscription", "customer": sub.provider_customer_id, "line_items[0][price]": price,
                                        "line_items[0][quantity]": 1, "success_url": f"{s.app_base_url}/app/billing?checkout=success",
                                        "cancel_url": f"{s.app_base_url}/app/billing?checkout=cancelled", "client_reference_id": str(ctx.org_id),
                                        "metadata[org_id]": str(ctx.org_id), "metadata[plan]": plan, "subscription_data[metadata][org_id]": str(ctx.org_id),
                                        "subscription_data[metadata][plan]": plan})
    return sess["url"]


def portal_url(db, ctx) -> str:
    sub = get_subscription(db, ctx.org_id)
    if not sub.provider_customer_id:
        raise RuntimeError("No Stripe customer for this organisation yet")
    return _post("/billing_portal/sessions", {"customer": sub.provider_customer_id, "return_url": f"{get_settings().app_base_url}/app/billing"})["url"]


def verify_signature(payload: bytes, header: str, secret: str, tolerance: int = 300) -> bool:
    import hmac
    import hashlib
    import time
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    ts, sig = parts.get("t"), parts.get("v1")
    if not ts or not sig or abs(time.time() - int(ts)) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def handle_event(db, event: dict):
    import uuid
    from app.models import Subscription
    from sqlalchemy import select
    obj = event["data"]["object"]
    t = event["type"]
    org_id = (obj.get("metadata") or {}).get("org_id") or obj.get("client_reference_id")
    if t in ("customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted", "checkout.session.completed"):
        if not org_id:
            return
        sub = db.scalar(select(Subscription).where(Subscription.org_id == uuid.UUID(org_id)))
        if not sub:
            return
        if t == "checkout.session.completed":
            sub.provider, sub.provider_subscription_id = "stripe", obj.get("subscription")
            sub.plan, sub.status, sub.trial_ends_at = obj["metadata"].get("plan", sub.plan), "active", None
        else:
            sub.provider, sub.provider_subscription_id = "stripe", obj["id"]
            sub.status = {"active": "active", "trialing": "trialing", "past_due": "past_due", "canceled": "canceled", "unpaid": "past_due"}.get(obj["status"], obj["status"])
            sub.plan = obj.get("metadata", {}).get("plan", sub.plan) if t != "customer.subscription.deleted" else "free"
            sub.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
            if obj.get("current_period_end"):
                sub.current_period_end = datetime.fromtimestamp(obj["current_period_end"], tz=timezone.utc)
    elif t in ("invoice.paid", "invoice.payment_failed"):
        sub = db.scalar(select(Subscription).where(Subscription.provider_customer_id == obj.get("customer")))
        if not sub:
            return
        if t == "invoice.payment_failed":
            sub.status = "past_due"
        if not db.scalar(select(Invoice).where(Invoice.provider_invoice_id == obj["id"])):
            db.add(Invoice(org_id=sub.org_id, number=obj.get("number") or obj["id"], amount_cents=obj.get("amount_paid") or obj.get("amount_due") or 0,
                           currency=obj.get("currency", "usd"), status="paid" if t == "invoice.paid" else "open",
                           description="Subscription", provider_invoice_id=obj["id"], hosted_url=obj.get("hosted_invoice_url")))
