from tests.conftest import run_jobs, set_plan, add_member
from tests.fixtures import POLICY_MD, MEETING_NOTES


def test_template_agent_runs_tools(client, owner):
    set_plan(owner.org_id, "professional")
    a = owner.post("/api/agents/from-template/project_management").json()
    run = owner.post(f"/api/agents/{a['id']}/runs", json={"input": f"Extract action items from these notes:\n{MEETING_NOTES}", "sync": True}).json()
    assert run["status"] == "succeeded", run
    tool_steps = [s for s in run["steps"] if s["type"] == "tool_call"]
    assert tool_steps and tool_steps[0]["tool"] == "extract_action_items" and tool_steps[0]["status"] == "ok"
    assert run["output"] and run["total_tokens"] > 0
    m = owner.get(f"/api/agents/{a['id']}/metrics").json()
    assert m["runs"] == 1 and m["succeeded"] == 1 and m["tool_usage"]


def test_async_run_via_worker(client, owner):
    set_plan(owner.org_id, "professional")
    owner.post("/api/documents", files={"file": ("policy.md", POLICY_MD.encode(), "text/markdown")})
    run_jobs()
    a = owner.post("/api/agents/from-template/customer_support").json()
    run = owner.post(f"/api/agents/{a['id']}/runs", json={"input": "search knowledge: what is the reimbursement deadline for receipts?"}).json()
    assert run["status"] == "queued"
    run_jobs()
    r = owner.get(f"/api/agents/runs/{run['id']}").json()
    assert r["status"] == "succeeded"
    assert any(s["tool"] == "search_knowledge" for s in r["steps"])


def test_sensitive_tool_requires_approval(client, owner):
    set_plan(owner.org_id, "professional")
    manager = add_member(owner, "manager")
    member = add_member(owner, "member")
    a = owner.post("/api/agents", json={"name": "Mailer", "instructions": "Send emails when asked to send email.", "tools": ["send_email"],
                                        "approval_required_tools": []}).json()
    run = member.post(f"/api/agents/{a['id']}/runs", json={"input": "send email to the customer", "sync": True}).json()
    assert run["status"] == "awaiting_approval" and run["pending_approvals"]
    aps = manager.get("/api/approvals").json()
    ap = next(x for x in aps if x["source_id"] == run["id"])
    assert member.post(f"/api/approvals/{ap['id']}/decide", json={"decision": "approved"}).status_code == 403  # members can't approve
    assert manager.post(f"/api/approvals/{ap['id']}/decide", json={"decision": "approved"}).status_code == 200
    assert manager.post(f"/api/approvals/{ap['id']}/decide", json={"decision": "approved"}).status_code == 400  # no double decision
    run_jobs()
    r = owner.get(f"/api/agents/runs/{run['id']}").json()
    assert r["status"] == "succeeded"
    sent = [s for s in r["steps"] if s["tool"] == "send_email" and s["type"] == "tool_call"]
    assert sent and sent[0]["status"] in ("ok", "error")  # executed only after approval


def test_rejected_approval(client, owner):
    set_plan(owner.org_id, "professional")
    a = owner.post("/api/agents", json={"name": "Hook", "instructions": "Send webhook payloads when asked.", "tools": ["send_webhook"]}).json()
    run = owner.post(f"/api/agents/{a['id']}/runs", json={"input": "send webhook now", "sync": True}).json()
    ap = owner.get("/api/approvals").json()[0]
    owner.post(f"/api/approvals/{ap['id']}/decide", json={"decision": "rejected", "note": "not today"})
    run_jobs()
    r = owner.get(f"/api/agents/runs/{run['id']}").json()
    assert r["status"] == "succeeded"
    assert any(s["type"] == "approval" and s["status"] == "rejected" for s in r["steps"])
    assert not any(s["type"] == "tool_call" and s["tool"] == "send_webhook" for s in r["steps"])


def test_tool_grants_and_validation(client, owner):
    set_plan(owner.org_id, "starter")
    r = owner.post("/api/agents", json={"name": "x", "instructions": "do things please", "tools": ["rm_rf"]})
    assert r.status_code == 400
    r = owner.post("/api/agents", json={"name": "x", "instructions": "do things please", "tools": ["fetch_url"]})
    assert r.status_code == 402  # advanced tool on starter plan
    manager = add_member(owner, "manager")
    viewer = add_member(owner, "viewer")
    a = manager.post("/api/agents", json={"name": "calc", "instructions": "Calculate numbers accurately.", "tools": ["calculate"]}).json()
    assert viewer.post(f"/api/agents/{a['id']}/runs", json={"input": "2+2"}).status_code == 403


def test_safe_calculator():
    from app.agents.tools import safe_eval
    import pytest
    assert safe_eval("2 + 3 * 4") == 14
    for bad in ["__import__('os').system('id')", "9**9**9", "open('x')", "[1,2]"]:
        with pytest.raises(Exception):
            safe_eval(bad)
