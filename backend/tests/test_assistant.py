from tests.conftest import run_jobs, set_plan, add_member
from tests.fixtures import POLICY_MD


def test_conversation_with_rag_and_metering(client, owner):
    set_plan(owner.org_id, "professional")
    owner.post("/api/documents", files={"file": ("policy.md", POLICY_MD.encode(), "text/markdown")})
    run_jobs()
    c = owner.post("/api/conversations", json={}).json()
    r = owner.post(f"/api/conversations/{c['id']}/messages", json={"content": "What is the home office allowance?"})
    assert r.status_code == 200, r.text
    msg = r.json()["assistant_message"]
    assert "300" in msg["content"] and msg["citations"]
    assert msg["meta"]["provider"] == "demo" and msg["meta"]["input_tokens"] > 0
    conv = owner.get(f"/api/conversations/{c['id']}").json()
    assert len(conv["messages"]) == 2 and conv["title"].startswith("What is the home office")
    usage = owner.get("/api/billing/usage").json()
    assert usage["ai_messages"]["used"] == 1
    exp = owner.get(f"/api/conversations/{c['id']}/export?format=md")
    assert exp.status_code == 200 and "home office" in exp.text


def test_plan_limit_enforced(client, owner):
    set_plan(owner.org_id, "free", limits={"ai_messages": 1})
    c = owner.post("/api/conversations", json={"use_knowledge": False}).json()
    assert owner.post(f"/api/conversations/{c['id']}/messages", json={"content": "hello"}).status_code == 200
    r = owner.post(f"/api/conversations/{c['id']}/messages", json={"content": "hello again"})
    assert r.status_code == 402 and r.json()["error"]["code"] == "plan_limit_reached"


def test_sharing_is_read_only_and_scoped(client, owner):
    set_plan(owner.org_id, "professional")
    m = add_member(owner, "member")
    c = owner.post("/api/conversations", json={"use_knowledge": False}).json()
    owner.post(f"/api/conversations/{c['id']}/messages", json={"content": "Draft a launch checklist"})
    assert m.get(f"/api/conversations/{c['id']}").status_code == 404
    assert owner.post(f"/api/conversations/{c['id']}/share", json={"user_ids": [m.user_id]}).status_code == 200
    assert m.get(f"/api/conversations/{c['id']}").status_code == 200
    assert m.post(f"/api/conversations/{c['id']}/messages", json={"content": "x"}).status_code == 403
    assert any(x["id"] == c["id"] for x in m.get("/api/conversations").json())


def test_summarize_extract_recommend(client, owner):
    set_plan(owner.org_id, "professional")
    s = owner.post("/api/assistant/summarize", json={"text": POLICY_MD}).json()
    assert s["summary"]
    e = owner.post("/api/assistant/extract", json={"text": "Invoice INV-77 from Acme Ltd, total 4500, contact billing@acme.example, due 2026-12-01",
                                                  "fields": [{"name": "email", "type": "string"}, {"name": "total", "type": "number"},
                                                             {"name": "due_date", "type": "date"}]}).json()
    assert e["data"]["email"] == "billing@acme.example" and e["data"]["total"] == 4500.0 and e["data"]["due_date"] == "2026-12-01"
    rec = owner.post("/api/assistant/recommend-tasks", json={"text": "Priya to send the proposal by Friday. Rahul will fix the login bug tomorrow."}).json()
    titles = [t["title"].lower() for t in rec["suggestions"]]
    assert any("proposal" in t for t in titles) and any("login" in t for t in titles)
    assert owner.post("/api/assistant/extract", json={"text": "x", "fields": [{"name": "bad name!", "type": "string"}]}).status_code == 422


def test_input_validation(client, owner):
    c = owner.post("/api/conversations", json={}).json()
    assert owner.post(f"/api/conversations/{c['id']}/messages", json={"content": "   "}).status_code == 400
    assert owner.post(f"/api/conversations/{c['id']}/messages", json={"content": "x" * 40000}).status_code == 422
    assert owner.post("/api/conversations", json={"model_route": "gpt-9000"}).status_code == 400
