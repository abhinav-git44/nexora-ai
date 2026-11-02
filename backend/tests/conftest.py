import os
import re
import uuid

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://nexora:nexora@localhost:5432/nexora_test")
os.environ["APP_ENV"] = "test"
os.environ["REDIS_URL"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["STORAGE_LOCAL_DIR"] = "/tmp/nexora-test-uploads"
os.environ["SUPER_ADMIN_EMAILS"] = "superadmin@example.com"
os.environ["MIXPANEL_TOKEN"] = ""

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import ratelimit


@pytest.fixture(scope="session", autouse=True)
def migrated():
    from app.core.db import engine
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public; DROP SCHEMA IF EXISTS datasets CASCADE;"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def no_ratelimit():
    ratelimit.ENABLED = False
    ratelimit.reset_local()
    yield
    ratelimit.ENABLED = False


@pytest.fixture(scope="session")
def client(migrated):
    from app.main import app
    with TestClient(app) as c:
        yield c


def run_jobs():
    from app.worker.queue import run_pending
    import app.worker.tasks  # noqa
    return run_pending(200)


class Actor:
    def __init__(self, client, token, org_id, email, user_id):
        self.client, self.token, self.org_id, self.email, self.user_id = client, token, org_id, email, user_id

    @property
    def h(self):
        return {"Authorization": f"Bearer {self.token}", "X-Org-Id": self.org_id}

    def get(self, url, **kw):
        return self.client.get(url, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def post(self, url, **kw):
        return self.client.post(url, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def patch(self, url, **kw):
        return self.client.patch(url, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def put(self, url, **kw):
        return self.client.put(url, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def delete(self, url, **kw):
        return self.client.delete(url, headers={**self.h, **kw.pop("headers", {})}, **kw)


PASSWORD = "Sup3rSecure!pass"


def register(client, email=None, org="Acme Ltd", name="Test User", password=PASSWORD) -> Actor:
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": password, "full_name": name, "organization_name": org})
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    return Actor(client, tok, me["organizations"][0]["id"] if me["organizations"] else None, email, me["user"]["id"])


def verify_email(actor: Actor):
    me = actor.client.get("/api/auth/me", headers={"Authorization": f"Bearer {actor.token}"}).json()
    if me["user"]["email_verified"]:
        return
    from app.core.db import SessionLocal
    from app.models import EmailOutbox
    from sqlalchemy import select
    with SessionLocal() as db:
        mail = db.scalars(select(EmailOutbox).where(EmailOutbox.to_email == actor.email, EmailOutbox.kind == "verify_email")
                          .order_by(EmailOutbox.created_at.desc())).first()
        token = re.search(r"token=([\w\-]+)", mail.body).group(1)
    assert actor.client.post("/api/auth/verify-email/confirm", json={"token": token}).status_code == 200


def add_member(owner: Actor, role: str) -> Actor:
    """Invite + register a member with the given role into owner's org."""
    verify_email(owner)
    email = f"{role}-{uuid.uuid4().hex[:6]}@example.com"
    r = owner.post("/api/orgs/current/invitations", json={"email": email, "role": role})
    assert r.status_code == 201, r.text
    from app.core.db import SessionLocal
    from app.models import EmailOutbox
    from sqlalchemy import select
    with SessionLocal() as db:
        body = db.scalars(select(EmailOutbox.body).where(EmailOutbox.to_email == email)).first()
    token = re.search(r"token=([\w\-]+)", body).group(1)
    r = owner.client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "full_name": f"{role.title()} Person", "invitation_token": token})
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    me = owner.client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert me["organizations"][0]["id"] == owner.org_id
    return Actor(owner.client, tok, owner.org_id, email, me["user"]["id"])


def set_plan(org_id, plan="professional", limits=None):
    from app.core.db import SessionLocal
    from app.core.plans import get_subscription
    with SessionLocal() as db:
        s = get_subscription(db, uuid.UUID(org_id))
        s.plan, s.status, s.trial_ends_at = plan, "active", None
        if limits is not None:
            s.custom_limits = limits
        db.commit()


@pytest.fixture
def owner(client):
    return register(client)


@pytest.fixture
def other_org(client):
    return register(client, org="Globex Corp")
