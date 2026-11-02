import re
from sqlalchemy import select
from tests.conftest import register, PASSWORD, verify_email
from app.core.db import SessionLocal
from app.models import EmailOutbox


def test_register_login_me(client):
    a = register(client, name="Ana Owner")
    r = client.post("/api/auth/login", json={"email": a.email, "password": PASSWORD})
    assert r.status_code == 200 and r.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
    assert me["user"]["email"] == a.email and me["organizations"][0]["role"] == "owner"


def test_duplicate_and_weak_password(client):
    a = register(client)
    assert client.post("/api/auth/register", json={"email": a.email, "password": PASSWORD, "full_name": "x"}).status_code == 409
    r = client.post("/api/auth/register", json={"email": "weak@example.com", "password": "alllowercase1", "full_name": "x"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "weak_password"


def test_wrong_password_and_lockout(client):
    a = register(client)
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": a.email, "password": "Wrong!pass123"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": a.email, "password": PASSWORD})
    assert r.status_code == 423


def test_unauthenticated_and_bad_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_refresh_rotation_and_logout(client):
    a = register(client)
    r1 = client.post("/api/auth/refresh")
    assert r1.status_code == 200
    old_cookie = client.cookies.get("nx_refresh")
    r2 = client.post("/api/auth/refresh")
    assert r2.status_code == 200 and client.cookies.get("nx_refresh") != old_cookie
    # replaying a rotated refresh token fails
    r3 = client.post("/api/auth/refresh", cookies={"nx_refresh": old_cookie})
    assert r3.status_code == 401
    client.post("/api/auth/logout")
    assert client.post("/api/auth/refresh").status_code == 401


def test_session_revocation_kills_access_token(client):
    a = register(client)
    sessions = client.get("/api/auth/sessions", headers={"Authorization": f"Bearer {a.token}"}).json()
    sid = sessions[0]["id"]
    assert client.delete(f"/api/auth/sessions/{sid}", headers={"Authorization": f"Bearer {a.token}"}).status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {a.token}"}).status_code == 401


def test_email_verification(client):
    a = register(client)
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {a.token}"}).json()
    assert me["user"]["email_verified"] is False
    verify_email(a)
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {a.token}"}).json()
    assert me["user"]["email_verified"] is True
    assert client.post("/api/auth/verify-email/confirm", json={"token": "bogus"}).status_code == 400


def test_password_reset_flow(client):
    a = register(client)
    assert client.post("/api/auth/forgot-password", json={"email": a.email}).status_code == 200
    assert client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"}).status_code == 200  # no enumeration
    with SessionLocal() as db:
        body = db.scalars(select(EmailOutbox.body).where(EmailOutbox.to_email == a.email, EmailOutbox.kind == "reset_password")).first()
    token = re.search(r"token=([\w\-]+)", body).group(1)
    new = "N3w!Password99"
    assert client.post("/api/auth/reset-password", json={"token": token, "password": new}).status_code == 200
    assert client.post("/api/auth/reset-password", json={"token": token, "password": new}).status_code == 400  # single use
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {a.token}"}).status_code == 401  # sessions revoked
    assert client.post("/api/auth/login", json={"email": a.email, "password": new}).status_code == 200


def test_profile_export_and_delete(client):
    a = register(client)
    h = {"Authorization": f"Bearer {a.token}"}
    assert client.patch("/api/auth/me", json={"full_name": "Renamed"}, headers=h).json()["full_name"] == "Renamed"
    exp = client.get("/api/auth/me/export", headers=h).json()
    assert exp["profile"]["email"] == a.email
    # sole owner cannot delete account without handling org
    r = client.post("/api/auth/me/delete", json={"password": PASSWORD, "confirm": "DELETE"}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "sole_owner"
