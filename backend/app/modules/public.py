"""Unauthenticated endpoints: workflow webhooks (HMAC), hosted forms, payment-provider webhooks, OAuth callbacks."""
import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core import ratelimit
from app.core.config import get_settings
from app.core.crypto import decrypt_str, encrypt_json
from app.core.db import get_db
from app.core.errors import AppError, not_found, bad_request
from app.core.security import verify_hmac
from app.models import Workflow, WorkflowVersion, FormSubmission, IntegrationConnection
from app.workflows.service import create_execution

router = APIRouter(prefix="/api/hooks", tags=["public"])
forms_router = APIRouter(prefix="/api/forms", tags=["public"])
ROUTERS = [router, forms_router]
settings = get_settings()
MAX_BODY = 256 * 1024


def _wf_by_token(db, token: str, trigger: str) -> Workflow:
    wf = db.scalar(select(Workflow).where(Workflow.webhook_token == token))
    if not wf or wf.trigger_type != trigger or wf.status != "published":
        raise not_found("Workflow")
    return wf


def _trigger_cfg(db, wf: Workflow) -> dict:
    v = db.scalar(select(WorkflowVersion).where(WorkflowVersion.workflow_id == wf.id, WorkflowVersion.version == wf.published_version))
    trig = next(n for n in v.definition["nodes"] if n["type"].startswith("trigger."))
    return (trig.get("data") or {}).get("config") or {}


@router.post("/workflows/{token}", status_code=202)
async def workflow_webhook(token: str, request: Request, db: Session = Depends(get_db)):
    ratelimit.enforce(f"hook:{token}", 60)
    body = await request.body()
    if len(body) > MAX_BODY:
        raise bad_request("Payload too large")
    wf = _wf_by_token(db, token, "webhook")
    cfg = _trigger_cfg(db, wf)
    if cfg.get("require_signature", True) not in (False, "false", "False"):
        sig = request.headers.get("x-nexora-signature", "")
        if not sig or not verify_hmac(decrypt_str(wf.webhook_secret_enc), body, sig):
            raise AppError(401, "invalid_signature", "Missing or invalid X-Nexora-Signature (HMAC-SHA256 of the raw body)")
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        raise bad_request("Body must be JSON")
    ex = create_execution(db, wf, "webhook", payload if isinstance(payload, dict) else {"data": payload})
    return {"accepted": True, "execution_id": str(ex.id)}


@forms_router.get("/{token}")
def get_form(token: str, db: Session = Depends(get_db)):
    wf = _wf_by_token(db, token, "form")
    cfg = _trigger_cfg(db, wf)
    return {"title": cfg.get("title") or wf.name, "description": wf.description,
            "fields": [f.strip() for f in str(cfg.get("fields", "")).split(",") if f.strip()]}


class FormIn(BaseModel):
    data: dict[str, str]
    website: str | None = None  # honeypot


@forms_router.post("/{token}", status_code=201)
def submit_form(token: str, body: FormIn, request: Request, db: Session = Depends(get_db)):
    ratelimit.enforce(f"form:{request.client.host if request.client else 'x'}:{token}", 10)
    wf = _wf_by_token(db, token, "form")
    if body.website:
        return {"ok": True}  # silently drop bots
    fields = [f.strip() for f in str(_trigger_cfg(db, wf).get("fields", "")).split(",") if f.strip()]
    data = {k: str(body.data.get(k, ""))[:5000] for k in fields}
    db.add(FormSubmission(org_id=wf.org_id, workflow_id=wf.id, data=data))
    create_execution(db, wf, "form", data)
    return {"ok": True}


@router.post("/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    from app.billing_stripe import verify_signature, handle_event
    if not settings.stripe_webhook_secret:
        raise AppError(501, "not_configured", "Stripe webhooks not configured")
    payload = await request.body()
    if not verify_signature(payload, request.headers.get("stripe-signature", ""), settings.stripe_webhook_secret):
        raise AppError(400, "invalid_signature", "Invalid Stripe signature")
    handle_event(db, json.loads(payload))
    return {"received": True}


@router.get("/oauth/{provider}")
def oauth_callback(provider: str, code: str, state: str, db: Session = Depends(get_db)):
    import httpx
    from datetime import datetime, timezone
    conn = db.scalar(select(IntegrationConnection).where(IntegrationConnection.oauth_state == state))
    if not conn or conn.provider not in ("google_workspace", "slack"):
        raise bad_request("Invalid OAuth state")
    if provider == "google":
        tok = httpx.post("https://oauth2.googleapis.com/token", timeout=10, data={
            "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
            "redirect_uri": f"{settings.api_base_url}/api/hooks/oauth/google", "grant_type": "authorization_code"}).json()
        ok = "access_token" in tok
    elif provider == "slack":
        tok = httpx.post("https://slack.com/api/oauth.v2.access", timeout=10, data={
            "code": code, "client_id": settings.slack_client_id, "client_secret": settings.slack_client_secret,
            "redirect_uri": f"{settings.api_base_url}/api/hooks/oauth/slack"}).json()
        ok = bool(tok.get("ok"))
        if ok:
            tok = {"webhook_url": tok.get("incoming_webhook", {}).get("url"), "team": tok.get("team", {}).get("name")}
    else:
        raise not_found("Provider")
    conn.oauth_state = None
    conn.status = "connected" if ok else "error"
    conn.last_error = None if ok else str(tok.get("error", "OAuth exchange failed"))[:300]
    conn.last_tested_at = datetime.now(timezone.utc)
    if ok:
        conn.encrypted_credentials = encrypt_json({k: v for k, v in tok.items() if isinstance(v, str)})
    return RedirectResponse(f"{settings.app_base_url}/app/integrations?connected={conn.provider if ok else 'error'}")
