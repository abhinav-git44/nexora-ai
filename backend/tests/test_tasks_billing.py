from datetime import datetime, timedelta, timezone
from tests.conftest import set_plan, add_member, register
from tests.fixtures import MEETING_NOTES


def test_task_crud_comments_activity_notifications(client, owner):
    m = add_member(owner, "member")
    t = owner.post("/api/tasks", json={"title": "Prepare board deck", "priority": "high", "assignee_id": m.user_id, "labels": ["board"],
                                       "due_date": "2020-01-01"}).json()
    assert t["assignee"]["email"] == m.email and t["overdue"] is True
    notes = m.get("/api/notifications").json()
    assert notes["unread"] >= 1 and any("Prepare board deck" in n["title"] for n in notes["items"])
    assert m.post(f"/api/notifications/{notes['items'][0]['id']}/read").status_code == 200
    assert m.post(f"/api/tasks/{t['id']}/comments", json={"body": "On it"}).status_code == 201
    u = m.patch(f"/api/tasks/{t['id']}", json={"status": "done"}).json()
    assert u["status"] == "done" and u["completed_at"]
    detail = owner.get(f"/api/tasks/{t['id']}").json()
    assert [a["action"] for a in detail["activity"]] == ["created", "commented", "updated"] and detail["comments"][0]["body"] == "On it"
    assert owner.get("/api/tasks?status=done").json()[0]["id"] == t["id"]
    att = owner.post(f"/api/tasks/{t['id']}/attachments", files={"file": ("brief.txt", b"hello", "text/plain")}).json()
    assert owner.get(f"/api/tasks/{t['id']}/attachments/{att['id']}").content == b"hello"
    outsider = register(client)
    assert owner.post("/api/tasks", json={"title": "x", "assignee_id": outsider.user_id}).status_code == 400  # cannot assign outside org
    assert owner.get("/api/tasks/summary").json()["by_status"]["done"] == 1


def test_ai_extracts_tasks_from_notes(client, owner):
    r = owner.post("/api/tasks/ai/extract", json={"text": MEETING_NOTES, "create": False}).json()
    titles = [s["title"].lower() for s in r["suggestions"]]
    assert any("vendor proposal" in t for t in titles) and any("onboarding checklist" in t for t in titles)
    assert any("churn" in t for t in titles) and not any("hiring plan" in t for t in titles)
    urgent = next(s for s in r["suggestions"] if "churn" in s["title"].lower())
    assert urgent["priority"] == "urgent"
    r = owner.post("/api/tasks/ai/extract", json={"text": MEETING_NOTES, "create": True}).json()
    assert len(r["created_task_ids"]) == len(r["suggestions"]) >= 4
    assert all(t["source"] == "ai" for t in owner.get("/api/tasks").json())
    assert owner.post("/api/tasks/ai/summary").json()["summary"]


def test_plans_upgrade_downgrade_invoice(client, owner):
    plans = client.get("/api/billing/plans").json()
    assert [p["key"] for p in plans["plans"]] == ["free", "starter", "professional", "enterprise"] and plans["billing_mode"] == "demo"
    sub = owner.get("/api/billing/subscription").json()
    assert sub["status"] == "trialing" and sub["plan"] == "professional"  # reverse trial on signup
    r = owner.post("/api/billing/change-plan", json={"plan": "starter"}).json()
    assert r["plan"] == "starter" and r["mode"] == "demo"
    inv = owner.get("/api/billing/invoices").json()
    assert inv and inv[0]["status"] == "demo" and inv[0]["amount"] == 49
    assert owner.post("/api/billing/change-plan", json={"plan": "enterprise"}).json()["error"]["code"] == "contact_sales"
    for i in range(3):
        owner.post("/api/workflows", json={"name": f"w{i}"})
    set_plan(owner.org_id, "starter")
    r = owner.post("/api/billing/change-plan", json={"plan": "free"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "downgrade_blocked"


def test_trial_expiry_falls_back_to_free(client, owner):
    from app.core.db import SessionLocal
    from app.core.plans import get_subscription
    import uuid
    with SessionLocal() as db:
        s = get_subscription(db, uuid.UUID(owner.org_id))
        s.trial_ends_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert owner.get("/api/billing/subscription").json()["plan"] == "free"


def test_instruction_prefix_not_in_task_title():
    from app.ai.providers.demo_provider import DemoProvider
    tasks = DemoProvider.extract_tasks("Extract action items from: Priya to send the renewal proposal by Friday. Rahul will update the checklist.")
    assert tasks[0]["title"].startswith("Send the renewal proposal") and tasks[0]["owner_name"] == "Priya"
    assert all("extract" not in t["title"].lower() for t in tasks)
    t = DemoProvider.extract_tasks("Action: review Q3 churn (urgent).")[0]
    assert t["owner_name"] is None and t["priority"] == "urgent" and t["title"].lower().startswith("review q3 churn")
