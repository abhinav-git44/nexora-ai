import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
import jwt
from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.errors import AppError, forbidden
from app.core.permissions import has_permission
from app.core.security import decode_access_token
from app.models import User, UserSession, Membership, Organization


@dataclass
class OrgContext:
    """Resolved per-request tenant context. Every tenant query must use ctx.org_id."""
    user: User
    org: Organization
    membership: Membership
    session_id: str | None = None
    ip: str | None = None

    @property
    def org_id(self) -> uuid.UUID:
        return self.org.id

    @property
    def role(self) -> str:
        return self.membership.role

    def can(self, permission: str) -> bool:
        return has_permission(self.role, permission)


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _bearer(request)
    if not token:
        raise AppError(401, "unauthenticated", "Authentication required")
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise AppError(401, "invalid_token", "Invalid or expired token")
    sess = db.get(UserSession, uuid.UUID(payload["sid"]))
    if not sess or sess.revoked_at or sess.expires_at < datetime.now(timezone.utc):
        raise AppError(401, "session_revoked", "Session is no longer valid")
    user = db.get(User, uuid.UUID(payload["sub"]))
    if not user or not user.is_active or user.deleted_at:
        raise AppError(401, "user_inactive", "Account is inactive")
    request.state.user = user
    request.state.session_id = str(sess.id)
    return user


def get_org_context(
    request: Request,
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgContext:
    if not x_org_id:
        raise AppError(400, "org_required", "X-Org-Id header is required")
    try:
        org_uuid = uuid.UUID(x_org_id)
    except ValueError:
        raise AppError(400, "org_invalid", "Invalid organisation id")
    m = db.scalar(select(Membership).where(Membership.org_id == org_uuid, Membership.user_id == user.id))
    if not m or m.status != "active":
        # Do not reveal whether the org exists.
        raise AppError(404, "not_found", "Organisation not found")
    org = m.organization
    if org.deleted_at:
        raise AppError(404, "not_found", "Organisation not found")
    if org.is_suspended:
        raise AppError(403, "org_suspended", "This organisation is suspended. Contact support.")
    ctx = OrgContext(user=user, org=org, membership=m, session_id=getattr(request.state, "session_id", None),
                     ip=request.client.host if request.client else None)
    request.state.org_id = str(org.id)
    return ctx


def require(permission: str):
    def dep(ctx: OrgContext = Depends(get_org_context)) -> OrgContext:
        if not ctx.can(permission):
            raise forbidden(f"Requires permission '{permission}' (your role: {ctx.role})")
        return ctx
    return dep


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_super_admin:
        raise AppError(404, "not_found", "Not found")  # hide admin surface
    return user
