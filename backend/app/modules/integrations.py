"""Module 10: Integrations hub."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.audit import audit_ctx, track
from app.core.config import get_settings
from app.core.crypto import encrypt_json, decrypt_json, mask
from app.core.db import get_db
from app.core.deps import OrgContext, require
from app.core.errors import not_found, bad_request, AppError
from app.core.plans import check_limit
from app.integrations.providers import CATALOG, test_connection, n8n_list_workflows
from app.models import IntegrationConnection, IntegrationLog
from app.modules.common import iso

router = APIRouter(prefix="/api/integrations", tags=["integrations"])
settings = get_settings()


def _log(db, org_id, provider, action, status, message=None):
    db.add(IntegrationLog(org_id=org_id, provider=provider, action=action, status=status, message=(message or "")[:1000]))


def conn_out(c: IntegrationConnection | None, key: str) -> dict:
    spec = CATALOG[key]
    d = {"key": key, **{k: v for k, v in spec.items()}, "connection": None}
    if spec.get("oauth") == "google":
        d["status"] = "available" if settings.google_client_id else "requires_config"
    if c:
        masked = {}
        if c.encrypted_credentials:
            creds = decrypt_json(c.encrypted_credentials)
            for f in spec["fields"]:
                if f["key"] in creds:
                    masked[f["key"]] = mask(creds[f["key"]]) if f.get("secret") else creds[f["key"]]
        d["connection"] = {"id": str(c.id), "status": c.status, "scopes": c.scopes, "last_tested_at": iso(c.last_tested_at),
                           "last_error": c.last_error, "connected_at": iso(c.created_at), "credentials": masked}
    return d


@router.get("")
def list_integrations(ctx: OrgContext = Depends(require("integrations.read")), db: Session = Depends(get_db)):
    conns = {c.provider: c for c in db.scalars(select(IntegrationConnection).where(IntegrationConnection.org_id == ctx.org_id))}
    return [conn_out(conns.get(k), k) for k in CATALOG]


class ConnectIn(BaseModel):
    credentials: dict[str, str]


@router.post("/{provider}/connect")
def connect(provider: str, body: ConnectIn, ctx: OrgContext = Depends(require("integrations.manage")), db: Session = Depends(get_db)):
    spec = CATALOG.get(provider)
    if not spec:
        raise not_found("Integration")
    if spec["status"] == "coming_soon" or spec["auth"] == "oauth":
        raise bad_request("This integration uses OAuth or is not yet available", "unsupported")
    missing = [f["key"] for f in spec["fields"] if not body.credentials.get(f["key"], "").strip()]
    if missing:
        raise bad_request(f"Missing: {', '.join(missing)}")
    existing = db.scalar(select(IntegrationConnection).where(IntegrationConnection.org_id == ctx.org_id, IntegrationConnection.provider == provider))
    if not existing or existing.status != "connected":
        check_limit(db, ctx.org_id, "integrations")
    creds = {f["key"]: body.credentials[f["key"]].strip() for f in spec["fields"]}
    ok, msg = test_connection(provider, creds)
    c = existing or IntegrationConnection(org_id=ctx.org_id, provider=provider, auth_type=spec["auth"], connected_by=ctx.user.id)
    c.encrypted_credentials, c.scopes, c.last_tested_at = encrypt_json(creds), spec["scopes"], datetime.now(timezone.utc)
    c.status, c.last_error = ("connected", None) if ok else ("error", msg)
    if not existing:
        db.add(c)
    db.flush()
    _log(db, ctx.org_id, provider, "connect", "success" if ok else "error", msg)
    audit_ctx(db, ctx, "integration.connected" if ok else "integration.connect_failed", "integration", c.id, {"provider": provider})
    if ok:
        track(db, "integration_connected", org_id=ctx.org_id, user_id=ctx.user.id, properties={"provider": provider})
    return conn_out(c, provider)


@router.post("/{provider}/test")
def test(provider: str, ctx: OrgContext = Depends(require("integrations.manage")), db: Session = Depends(get_db)):
    c = db.scalar(select(IntegrationConnection).where(IntegrationConnection.org_id == ctx.org_id, IntegrationConnection.provider == provider))
    if not c or not c.encrypted_credentials:
        raise not_found("Connection")
    ok, msg = test_connection(provider, decrypt_json(c.encrypted_credentials))
    c.last_tested_at, c.status, c.last_error = datetime.now(timezone.utc), "connected" if ok else "error", None if ok else msg
    _log(db, ctx.org_id, provider, "test", "success" if ok else "error", msg)
    return conn_out(c, provider)


@router.delete("/{provider}")
def disconnect(provider: str, ctx: OrgContext = Depends(require("integrations.manage")), db: Session = Depends(get_db)):
    c = db.scalar(select(IntegrationConnection).where(IntegrationConnection.org_id == ctx.org_id, IntegrationConnection.provider == provider))
    if not c:
        raise not_found("Connection")
    # Revoke: credentials are destroyed, not just hidden.
    c.encrypted_credentials, c.status, c.scopes = None, "disconnected", []
    _log(db, ctx.org_id, provider, "disconnect", "success")
    audit_ctx(db, ctx, "integration.disconnected", "integration", c.id, {"provider": provider})
    track(db, "integration_disconnected", org_id=ctx.org_id, user_id=ctx.user.id, properties={"provider": provider})
    return conn_out(c, provider)


@router.get("/{provider}/logs")
def logs(provider: str, ctx: OrgContext = Depends(require("integrations.read")), db: Session = Depends(get_db)):
    rows = db.scalars(select(IntegrationLog).where(IntegrationLog.org_id == ctx.org_id, IntegrationLog.provider == provider)
                      .order_by(IntegrationLog.created_at.desc()).limit(100)).all()
    return [{"action": r.action, "status": r.status, "message": r.message, "created_at": iso(r.created_at)} for r in rows]


@router.get("/n8n/workflows")
def n8n_workflows(ctx: OrgContext = Depends(require("integrations.read")), db: Session = Depends(get_db)):
    c = db.scalar(select(IntegrationConnection).where(IntegrationConnection.org_id == ctx.org_id, IntegrationConnection.provider == "n8n",
                                                      IntegrationConnection.status == "connected"))
    if not c:
        raise AppError(409, "not_connected", "Connect n8n first")
    try:
        return n8n_list_workflows(c)
    except Exception as e:
        _log(db, ctx.org_id, "n8n", "list_workflows", "error", str(e))
        raise AppError(502, "n8n_error", "Could not reach n8n")


@router.get("/{provider}/oauth/start")
def oauth_start(provider: str, ctx: OrgContext = Depends(require("integrations.manage")), db: Session = Depends(get_db)):
    from urllib.parse import urlencode
    from app.core.security import new_token
    spec = CATALOG.get(provider)
    if not spec or not spec.get("oauth"):
        raise not_found("OAuth integration")
    state = new_token(24)
    if spec["oauth"] == "google":
        if not settings.google_client_id:
            raise AppError(501, "not_configured", "GOOGLE_CLIENT_ID is not configured on this server")
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "client_id": settings.google_client_id, "redirect_uri": f"{settings.api_base_url}/api/hooks/oauth/google", "response_type": "code",
            "scope": "https://www.googleapis.com/auth/drive.readonly", "access_type": "offline", "prompt": "consent", "state": state})
    elif spec["oauth"] == "slack":
        if not settings.slack_client_id:
            raise AppError(501, "not_configured", "SLACK_CLIENT_ID is not configured; use an incoming webhook URL instead")
        url = "https://slack.com/oauth/v2/authorize?" + urlencode({"client_id": settings.slack_client_id, "scope": "incoming-webhook",
                                                                   "redirect_uri": f"{settings.api_base_url}/api/hooks/oauth/slack", "state": state})
    else:
        raise not_found("OAuth integration")
    c = db.scalar(select(IntegrationConnection).where(IntegrationConnection.org_id == ctx.org_id, IntegrationConnection.provider == provider))
    if not c:
        c = IntegrationConnection(org_id=ctx.org_id, provider=provider, auth_type="oauth", status="pending", connected_by=ctx.user.id)
        db.add(c)
    c.oauth_state = state
    return {"url": url}
