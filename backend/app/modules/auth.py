"""Module 1: authentication, sessions, verification, password reset, profile, account deletion, data export."""
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.audit import audit, track
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.email import send_email
from app.core.errors import AppError, bad_request
from app.core import ratelimit
from app.core.plans import TRIAL_DAYS, TRIAL_PLAN
from app.core.security import (hash_password, verify_password, validate_password_strength, new_token, sha256, create_access_token)
from app.models import User, UserSession, AuthToken, Organization, Membership, Workspace, Subscription, Invitation
from app.modules.common import slugify, iso

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()
REFRESH_COOKIE = "nx_refresh"


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    organization_name: str | None = Field(default=None, max_length=200)
    invitation_token: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str


class ResetIn(BaseModel):
    token: str
    password: str


class ProfileIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    job_title: str | None = Field(default=None, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=500)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


def user_out(u: User) -> dict:
    return {"id": str(u.id), "email": u.email, "full_name": u.full_name, "job_title": u.job_title, "avatar_url": u.avatar_url,
            "email_verified": bool(u.email_verified_at), "is_super_admin": u.is_super_admin, "created_at": iso(u.created_at),
            "onboarding_completed": bool(u.onboarding_completed_at)}


def _issue(db: Session, user: User, request: Request, response: Response) -> dict:
    raw = new_token(48)
    sess = UserSession(user_id=user.id, refresh_token_hash=sha256(raw), user_agent=(request.headers.get("user-agent") or "")[:500],
                       ip=request.client.host if request.client else None,
                       expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_ttl_days))
    db.add(sess)
    db.flush()
    response.set_cookie(REFRESH_COOKIE, raw, httponly=True, secure=settings.cookie_secure, samesite="lax",
                        max_age=settings.refresh_ttl_days * 86400, path="/api/auth")
    return {"access_token": create_access_token(str(user.id), str(sess.id)), "token_type": "bearer",
            "expires_in": settings.jwt_access_ttl_minutes * 60, "user": user_out(user)}


def _send_verification(db: Session, user: User):
    raw = new_token()
    db.add(AuthToken(user_id=user.id, kind="verify_email", token_hash=sha256(raw), expires_at=datetime.now(timezone.utc) + timedelta(days=2)))
    send_email(db, user.email, "Verify your NEXORA AI email",
               f"Hi {user.full_name},\n\nConfirm your email: {settings.app_base_url}/verify-email?token={raw}\n\nThis link expires in 48 hours.",
               "verify_email")


def create_org_for(db: Session, user: User, name: str) -> Organization:
    org = Organization(name=name, slug=slugify(name))
    db.add(org)
    db.flush()
    db.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
    db.add(Workspace(org_id=org.id, name="General", description="Default workspace", created_by=user.id, is_default=True))
    db.add(Subscription(org_id=org.id, plan=TRIAL_PLAN, status="trialing", provider="none",
                        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)))
    db.flush()
    track(db, "org_created", org_id=org.id, user_id=user.id)
    track(db, "workspace_created", org_id=org.id, user_id=user.id, properties={"default": True})
    return org


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ratelimit.enforce(f"register:{request.client.host if request.client else 'x'}", 10, 3600)
    email = body.email.lower()
    if err := validate_password_strength(body.password):
        raise bad_request(err, "weak_password")
    if db.scalar(select(User).where(User.email == email)):
        raise AppError(409, "email_taken", "An account with this email already exists")
    admins = {e.strip().lower() for e in settings.super_admin_emails.split(",") if e.strip()}
    user = User(email=email, password_hash=hash_password(body.password), full_name=body.full_name.strip(), is_super_admin=email in admins)
    db.add(user)
    db.flush()
    joined_org = None
    if body.invitation_token:
        inv = db.scalar(select(Invitation).where(Invitation.token_hash == sha256(body.invitation_token)))
        if inv and not inv.accepted_at and not inv.revoked_at and inv.expires_at > datetime.now(timezone.utc) and inv.email == email:
            db.add(Membership(org_id=inv.org_id, user_id=user.id, role=inv.role))
            inv.accepted_at = datetime.now(timezone.utc)
            user.email_verified_at = datetime.now(timezone.utc)  # possession of the invite link proves the mailbox
            joined_org = inv.org_id
            track(db, "invitation_accepted", org_id=inv.org_id, user_id=user.id)
    if not joined_org:
        create_org_for(db, user, body.organization_name or f"{body.full_name.split()[0]}'s Company")
        _send_verification(db, user)
    audit(db, "user.registered", actor_id=user.id, target_type="user", target_id=user.id, ip=request.client.host if request.client else None)
    track(db, "user_signed_up", user_id=user.id, properties={"via_invite": bool(joined_org)})
    return _issue(db, user, request, response)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "x"
    ratelimit.enforce(f"login:{ip}", 20, 60)
    ratelimit.enforce(f"login:{body.email.lower()}", 10, 60)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    now = datetime.now(timezone.utc)
    if user and user.locked_until and user.locked_until > now:
        raise AppError(423, "account_locked", "Too many failed attempts. Try again in a few minutes or reset your password.")
    if not user or not verify_password(body.password, user.password_hash):
        if user:
            user.failed_login_count += 1
            if user.failed_login_count >= 5:
                user.locked_until, user.failed_login_count = now + timedelta(minutes=15), 0
            audit(db, "auth.login_failed", actor_id=user.id, ip=ip)
            db.commit()
        raise AppError(401, "invalid_credentials", "Incorrect email or password")
    if not user.is_active or user.deleted_at:
        raise AppError(403, "account_disabled", "This account has been deactivated")
    user.failed_login_count, user.locked_until, user.last_login_at = 0, None, now
    audit(db, "auth.login", actor_id=user.id, ip=ip)
    track(db, "user_logged_in", user_id=user.id)
    return _issue(db, user, request, response)


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise AppError(401, "no_refresh", "Not signed in")
    sess = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == sha256(raw)))
    now = datetime.now(timezone.utc)
    if not sess or sess.revoked_at or sess.expires_at < now:
        response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
        raise AppError(401, "session_expired", "Session expired")
    user = db.get(User, sess.user_id)
    if not user or not user.is_active or user.deleted_at:
        raise AppError(401, "user_inactive", "Account is inactive")
    # Rotate refresh token on every use (limits replay window of a stolen cookie).
    new_raw = new_token(48)
    sess.refresh_token_hash, sess.last_used_at = sha256(new_raw), now
    response.set_cookie(REFRESH_COOKIE, new_raw, httponly=True, secure=settings.cookie_secure, samesite="lax",
                        max_age=settings.refresh_ttl_days * 86400, path="/api/auth")
    return {"access_token": create_access_token(str(user.id), str(sess.id)), "token_type": "bearer",
            "expires_in": settings.jwt_access_ttl_minutes * 60, "user": user_out(user)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        sess = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == sha256(raw)))
        if sess:
            sess.revoked_at = datetime.now(timezone.utc)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Membership).where(Membership.user_id == user.id, Membership.status == "active")).all()
    orgs = [{"id": str(m.org_id), "name": m.organization.name, "slug": m.organization.slug, "role": m.role}
            for m in rows if not m.organization.deleted_at]
    return {"user": user_out(user), "organizations": orgs}


@router.patch("/me")
def update_profile(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(user, k, v.strip() if isinstance(v, str) else v)
    return user_out(user)


@router.post("/me/onboarding-complete")
def onboarding_complete(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.onboarding_completed_at:
        user.onboarding_completed_at = datetime.now(timezone.utc)
        track(db, "onboarding_completed", user_id=user.id)
    return user_out(user)


@router.post("/change-password")
def change_password(body: PasswordChangeIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise bad_request("Current password is incorrect", "invalid_password")
    if err := validate_password_strength(body.new_password):
        raise bad_request(err, "weak_password")
    user.password_hash = hash_password(body.new_password)
    # Revoke all other sessions.
    for s in db.scalars(select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))):
        if str(s.id) != getattr(request.state, "session_id", None):
            s.revoked_at = datetime.now(timezone.utc)
    audit(db, "auth.password_changed", actor_id=user.id)
    return {"ok": True}


@router.post("/verify-email/request")
def request_verification(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ratelimit.enforce(f"verify:{user.id}", 5, 3600)
    if user.email_verified_at:
        return {"ok": True, "already_verified": True}
    _send_verification(db, user)
    return {"ok": True}


@router.post("/verify-email/confirm")
def confirm_verification(body: TokenIn, db: Session = Depends(get_db)):
    tok = db.scalar(select(AuthToken).where(AuthToken.token_hash == sha256(body.token), AuthToken.kind == "verify_email"))
    if not tok or tok.used_at or tok.expires_at < datetime.now(timezone.utc):
        raise bad_request("Verification link is invalid or has expired", "invalid_token")
    tok.used_at = datetime.now(timezone.utc)
    user = db.get(User, tok.user_id)
    user.email_verified_at = datetime.now(timezone.utc)
    track(db, "email_verified", user_id=user.id)
    return {"ok": True}


@router.post("/forgot-password")
def forgot_password(body: EmailIn, request: Request, db: Session = Depends(get_db)):
    ratelimit.enforce(f"forgot:{request.client.host if request.client else 'x'}", 5, 900)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user and user.is_active:
        raw = new_token()
        db.add(AuthToken(user_id=user.id, kind="reset_password", token_hash=sha256(raw), expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        send_email(db, user.email, "Reset your NEXORA AI password",
                   f"Reset your password: {settings.app_base_url}/reset-password?token={raw}\n\nThis link expires in 1 hour. "
                   "If you did not request this, ignore this email.", "reset_password")
        audit(db, "auth.password_reset_requested", actor_id=user.id)
    return {"ok": True}  # identical response whether or not the account exists


@router.post("/reset-password")
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    tok = db.scalar(select(AuthToken).where(AuthToken.token_hash == sha256(body.token), AuthToken.kind == "reset_password"))
    if not tok or tok.used_at or tok.expires_at < datetime.now(timezone.utc):
        raise bad_request("Reset link is invalid or has expired", "invalid_token")
    if err := validate_password_strength(body.password):
        raise bad_request(err, "weak_password")
    tok.used_at = datetime.now(timezone.utc)
    user = db.get(User, tok.user_id)
    user.password_hash, user.failed_login_count, user.locked_until = hash_password(body.password), 0, None
    for s in db.scalars(select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))):
        s.revoked_at = datetime.now(timezone.utc)
    audit(db, "auth.password_reset", actor_id=user.id)
    return {"ok": True}


@router.get("/sessions")
def list_sessions(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None),
                                                UserSession.expires_at > datetime.now(timezone.utc)).order_by(UserSession.last_used_at.desc())).all()
    current = getattr(request.state, "session_id", None)
    return [{"id": str(s.id), "user_agent": s.user_agent, "ip": s.ip, "created_at": iso(s.created_at), "last_used_at": iso(s.last_used_at),
             "current": str(s.id) == current} for s in rows]


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(UserSession, session_id)
    if not s or s.user_id != user.id:
        raise AppError(404, "not_found", "Session not found")
    s.revoked_at = datetime.now(timezone.utc)
    audit(db, "auth.session_revoked", actor_id=user.id, target_type="session", target_id=s.id)
    return {"ok": True}


@router.get("/me/export")
def export_my_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """DPDP/GDPR-style data portability: everything NEXORA stores that is personal to this user."""
    from app.models import Conversation, Message, Task, Notification
    convs = db.scalars(select(Conversation).where(Conversation.user_id == user.id)).all()
    msgs = db.scalars(select(Message).where(Message.conversation_id.in_([c.id for c in convs]))).all() if convs else []
    tasks = db.scalars(select(Task).where((Task.created_by == user.id) | (Task.assignee_id == user.id))).all()
    notes = db.scalars(select(Notification).where(Notification.user_id == user.id)).all()
    audit(db, "user.data_exported", actor_id=user.id)
    return {"exported_at": datetime.now(timezone.utc).isoformat(), "profile": user_out(user),
            "conversations": [{"id": str(c.id), "title": c.title, "messages": [{"role": m.role, "content": m.content, "created_at": iso(m.created_at)}
                                                                              for m in msgs if m.conversation_id == c.id]} for c in convs],
            "tasks": [{"id": str(t.id), "title": t.title, "status": t.status} for t in tasks],
            "notifications": [{"title": n.title, "created_at": iso(n.created_at)} for n in notes]}


class DeleteAccountIn(BaseModel):
    password: str
    confirm: str


@router.post("/me/delete")
def delete_account(body: DeleteAccountIn, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.confirm != "DELETE" or not verify_password(body.password, user.password_hash):
        raise bad_request("Type DELETE and enter your password to confirm", "confirmation_required")
    owned = db.scalars(select(Membership).where(Membership.user_id == user.id, Membership.role == "owner", Membership.status == "active")).all()
    for m in owned:
        others = db.scalars(select(Membership).where(Membership.org_id == m.org_id, Membership.role == "owner", Membership.user_id != user.id)).all()
        if not others and not m.organization.deleted_at:
            raise bad_request(f"You are the only owner of '{m.organization.name}'. Transfer ownership or delete the organisation first.",
                              "sole_owner")
    now = datetime.now(timezone.utc)
    user.deleted_at, user.is_active = now, False
    user.email = f"deleted+{user.id.hex}@deleted.nexora"
    user.full_name, user.password_hash, user.avatar_url, user.job_title = "Deleted user", None, None, None
    for s in db.scalars(select(UserSession).where(UserSession.user_id == user.id)):
        s.revoked_at = now
    for m in db.scalars(select(Membership).where(Membership.user_id == user.id)):
        m.status = "deactivated"
    audit(db, "user.deleted", actor_id=user.id, target_type="user", target_id=user.id)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    return {"ok": True}


# ---------------- Social authentication (Google OIDC) — active only when GOOGLE_CLIENT_ID/SECRET are configured -------------
@router.get("/providers")
def auth_providers():
    return {"google": bool(settings.google_client_id and settings.google_client_secret)}


@router.get("/oauth/google/start")
def google_start(response: Response):
    if not (settings.google_client_id and settings.google_client_secret):
        raise AppError(501, "not_configured", "Google sign-in is not configured on this server")
    from urllib.parse import urlencode
    state = new_token(16)
    response.set_cookie("nx_oauth_state", state, httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=600, path="/api/auth")
    q = urlencode({"client_id": settings.google_client_id, "redirect_uri": f"{settings.app_base_url}/api/auth/oauth/google/callback",
                   "response_type": "code", "scope": "openid email profile", "state": state, "prompt": "select_account"})
    return {"url": f"https://accounts.google.com/o/oauth2/v2/auth?{q}"}


@router.get("/oauth/google/callback")
def google_callback(code: str, state: str, request: Request, db: Session = Depends(get_db)):
    import httpx
    from fastapi.responses import RedirectResponse
    from app.models import OAuthAccount
    if not settings.google_client_id or state != request.cookies.get("nx_oauth_state"):
        raise bad_request("Invalid OAuth state", "oauth_state")
    tok = httpx.post("https://oauth2.googleapis.com/token", timeout=10, data={
        "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
        "redirect_uri": f"{settings.app_base_url}/api/auth/oauth/google/callback", "grant_type": "authorization_code"}).json()
    info = httpx.get("https://openidconnect.googleapis.com/v1/userinfo", timeout=10,
                     headers={"Authorization": f"Bearer {tok.get('access_token')}"}).json()
    if not info.get("email_verified"):
        raise bad_request("Google account email is not verified")
    link = db.scalar(select(OAuthAccount).where(OAuthAccount.provider == "google", OAuthAccount.provider_user_id == info["sub"]))
    user = db.get(User, link.user_id) if link else db.scalar(select(User).where(User.email == info["email"].lower()))
    if not user:
        user = User(email=info["email"].lower(), full_name=info.get("name", ""), email_verified_at=datetime.now(timezone.utc))
        db.add(user)
        db.flush()
        create_org_for(db, user, f"{(info.get('given_name') or 'My')}'s Company")
        track(db, "user_signed_up", user_id=user.id, properties={"method": "google"})
    if not link:
        db.add(OAuthAccount(user_id=user.id, provider="google", provider_user_id=info["sub"]))
    redirect = RedirectResponse(f"{settings.app_base_url}/app")
    _issue(db, user, request, redirect)
    return redirect
