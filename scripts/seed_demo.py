"""Seed a clearly-labelled DEMO organisation by driving the real API (so every metric shown is a genuine record of these
synthetic actions — nothing is inserted directly into analytics tables).

Usage:  cd backend && .venv/bin/python ../scripts/seed_demo.py
Logins: demo.owner@example.com / DemoPassw0rd!   (also demo.manager@, demo.member@)   super admin: admin@example.com
"""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("RUN_WORKER_IN_PROCESS", "false")
os.environ.setdefault("SUPER_ADMIN_EMAILS", "admin@example.com")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.models import EmailOutbox, User  # noqa: E402
from app.worker.queue import run_pending  # noqa: E402
import app.worker.tasks  # noqa: E402,F401

PW = "DemoPassw0rd!"
DATA = Path(__file__).parent / "sample-data"
c = TestClient(fastapi_app)


def token_from_mail(email, kind):
    with SessionLocal() as db:
        body = db.scalars(select(EmailOutbox.body).where(EmailOutbox.to_email == email, EmailOutbox.kind == kind).order_by(EmailOutbox.created_at.desc())).first()
    return re.search(r"token=([\w\-]+)", body).group(1)


def login_or_register(email, name, org=None, invite=None):
    r = c.post("/api/auth/login", json={"email": email, "password": PW})
    if r.status_code == 200:
        return r.json()["access_token"]
    body = {"email": email, "password": PW, "full_name": name}
    if org:
        body["organization_name"] = org
    if invite:
        body["invitation_token"] = invite
    r = c.post("/api/auth/register", json=body)
    r.raise_for_status()
    return r.json()["access_token"]


def main():
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == "demo.owner@example.com")):
            print("Demo data already present. Drop the database to reseed.")
            return
    tok = login_or_register("demo.owner@example.com", "Priya Sharma", org="Northwind Operations (Demo)")
    c.post("/api/auth/verify-email/confirm", json={"token": token_from_mail("demo.owner@example.com", "verify_email")})
    me = c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    org = me["organizations"][0]["id"]
    H = {"Authorization": f"Bearer {tok}", "X-Org-Id": org}
    c.patch("/api/orgs/current", headers=H, json={"industry": "B2B SaaS", "size": "51-200"})
    c.post("/api/auth/me/onboarding-complete", headers=H)
    team = {}
    for email, name, role in [("demo.manager@example.com", "Rahul Verma", "manager"), ("demo.member@example.com", "Meera Iyer", "member")]:
        c.post("/api/orgs/current/invitations", headers=H, json={"email": email, "role": role})
        t = login_or_register(email, name, invite=token_from_mail(email, "invitation"))
        team[role] = {"Authorization": f"Bearer {t}", "X-Org-Id": org}
    login_or_register("admin@example.com", "Platform Admin", org="NEXORA Platform (internal)")

    for f in ["expense-policy.md", "customer-onboarding-sop.md", "security-faq.md"]:
        c.post("/api/documents", headers=H, files={"file": (f, (DATA / f).read_bytes(), "text/markdown")}, data={"tags": "policy" if "policy" in f else "operations"})
    run_pending(100)
    c.post("/api/datasets", headers=H, files={"file": ("sales-2026.csv", (DATA / "sales-2026.csv").read_bytes(), "text/csv")}, data={"name": "Sales 2026"})

    ds = c.get("/api/datasets", headers=H).json()[0]
    for q in ["Which customers generated the most revenue?", "What is the monthly revenue trend?", "Which category has the highest growth?",
              "top 5 products by revenue"]:
        c.post(f"/api/datasets/{ds['id']}/query", headers=H, json={"question": q})

    conv = c.post("/api/conversations", headers=H, json={}).json()
    for q in ["Who needs to approve a 7,000 USD expense?", "How long does a standard customer implementation take?",
              "How quickly are Severity 1 incidents acknowledged?"]:
        c.post(f"/api/conversations/{conv['id']}/messages", headers=H, json={"content": q})

    pm = c.post("/api/agents/from-template/project_management", headers=H).json()
    c.post("/api/agents/from-template/customer_support", headers=H)
    c.post("/api/agents/from-template/data_analytics", headers=H)
    c.post(f"/api/agents/{pm['id']}/runs", headers=H, json={"sync": True, "input": "Extract action items from: Priya to send the renewal proposal to Asha Traders by Friday. "
                                                                              "Rahul will update the onboarding checklist next week. Action: review Q3 churn (urgent)."})

    for key in ["lead_intake", "doc_summary_alert", "meeting_notes_to_tasks"]:
        w = c.post(f"/api/workflows/from-template/{key}", headers=H).json()
        c.post(f"/api/workflows/{w['id']}/publish", headers=H)
        if key == "meeting_notes_to_tasks":
            c.post(f"/api/workflows/{w['id']}/run", headers=H, json={"input": {"notes": "Meera to prepare the QBR deck for Chola Foods. Rahul to fix SSO bug."}})
        if key == "lead_intake":
            token = c.get(f"/api/workflows/{w['id']}", headers=H).json()["webhook_url"].rsplit("/", 1)[-1]
            c.post(f"/api/forms/{token}", json={"data": {"name": "Arjun Rao", "email": "arjun@example.org", "company": "Kaveri Logistics", "budget": "12000",
                                                          "message": "Interested in workflow automation for 40 users."}})
    run_pending(100)

    c.post("/api/tasks/ai/extract", headers=team["manager"], json={"create": True, "text": "Ops review notes:\n- Rahul to renegotiate the courier contract by Friday.\n"
                                                                                       "- Meera will draft the new refund macro tomorrow.\n- Action: audit stale CRM records (important)."})
    for t in [("Finalise Q4 hiring plan", "high", "in_progress"), ("Publish updated expense policy", "medium", "in_review"),
              ("Set up SSO for the finance team", "urgent", "todo"), ("Archive 2025 vendor contracts", "low", "done")]:
        c.post("/api/tasks", headers=H, json={"title": t[0], "priority": t[1], "status": t[2]})
    print("Seeded demo organisation 'Northwind Operations (Demo)'.")
    print("Login: demo.owner@example.com /", PW, "| super admin: admin@example.com /", PW)


if __name__ == "__main__":
    main()
