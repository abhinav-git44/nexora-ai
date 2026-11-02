import json
from tests.conftest import run_jobs, set_plan
from app.core.security import hmac_sha256


def N(i, t, **cfg):
    return {"id": i, "type": t, "position": {"x": 0, "y": 0}, "data": {"label": i, "config": cfg}}


def E(s, t, h=None):
    return {"id": f"{s}-{t}", "source": s, "target": t, "sourceHandle": h}


def mk(owner, nodes, edges, name="wf"):
    w = owner.post("/api/workflows", json={"name": name, "definition": {"nodes": nodes, "edges": edges}}).json()
    return w


def test_validation(client, owner):
    set_plan(owner.org_id, "professional")
    w = mk(owner, [N("a", "action.create_task", title="x")], [])
    v = owner.post(f"/api/workflows/{w['id']}/validate").json()
    assert not v["valid"] and any("exactly one trigger" in e["message"] for e in v["errors"])
    w = mk(owner, [N("t", "trigger.manual"), N("a", "logic.if", left="1", operator="equals", right="1"), N("b", "action.create_task", title="x")],
           [E("t", "a"), E("a", "b", "true"), E("b", "a")])
    v = owner.post(f"/api/workflows/{w['id']}/validate").json()
    assert any("cycle" in e["message"] for e in v["errors"])
    w = mk(owner, [N("t", "trigger.schedule", cron="* * * * *"), N("b", "action.create_task")], [E("t", "b")])
    errs = owner.post(f"/api/workflows/{w['id']}/validate").json()["errors"]
    assert any("5 minutes" in e["message"] for e in errs) and any("required" in e["message"] for e in errs)
    assert owner.post(f"/api/workflows/{w['id']}/publish").status_code == 400


def test_branching_execution_and_versioning(client, owner):
    set_plan(owner.org_id, "professional")
    nodes = [N("t", "trigger.manual"), N("check", "logic.if", left="{{trigger.amount}}", operator="greater_than", right="1000"),
             N("big", "action.create_task", title="Review large deal {{trigger.customer}}", priority="high"),
             N("small", "action.update_record", collection="deals", match_field="customer", match_value="{{trigger.customer}}",
               data='{"customer": "{{trigger.customer}}", "amount": "{{trigger.amount}}"}')]
    w = mk(owner, nodes, [E("t", "check"), E("check", "big", "true"), E("check", "small", "false")])
    assert owner.post(f"/api/workflows/{w['id']}/publish").json()["published_version"] == 1
    ex = owner.post(f"/api/workflows/{w['id']}/run", json={"input": {"amount": 5000, "customer": "Acme"}}).json()
    run_jobs()
    ex = owner.get(f"/api/workflows/executions/{ex['id']}").json()
    assert ex["status"] == "succeeded", ex
    ran = {l["node_id"] for l in ex["logs"]}
    assert "big" in ran and "small" not in ran
    assert any(t["title"] == "Review large deal Acme" for t in owner.get("/api/tasks").json())
    ex2 = owner.post(f"/api/workflows/{w['id']}/run", json={"input": {"amount": 10, "customer": "Tiny"}, "sync": True}).json()
    assert ex2["status"] == "succeeded"
    assert owner.post(f"/api/workflows/{w['id']}/publish").json()["published_version"] == 2
    a = owner.get(f"/api/workflows/{w['id']}/analytics").json()
    assert a["total"] == 2 and a["succeeded"] == 2


def test_failure_and_retry(client, owner):
    set_plan(owner.org_id, "professional")
    w = mk(owner, [N("t", "trigger.manual"), N("mail", "action.send_email", to="{{trigger.email}}", subject="Hi", body="Hello")], [E("t", "mail")])
    owner.post(f"/api/workflows/{w['id']}/publish")
    ex = owner.post(f"/api/workflows/{w['id']}/run", json={"input": {"email": "not-an-email"}, "sync": True}).json()
    assert ex["status"] == "failed" and "Invalid recipient" in ex["error"]
    r = owner.post(f"/api/workflows/executions/{ex['id']}/retry").json()
    assert r["attempt"] == 2 and r["retry_of"] == ex["id"]
    run_jobs()


def test_approval_and_delay_resume(client, owner):
    set_plan(owner.org_id, "professional")
    nodes = [N("t", "trigger.manual"), N("ap", "logic.approval", title="Approve payout"), N("wait", "logic.delay", seconds="0"),
             N("ok", "action.create_task", title="Payout approved"), N("no", "action.create_task", title="Payout rejected")]
    w = mk(owner, nodes, [E("t", "ap"), E("ap", "wait", "approved"), E("wait", "ok"), E("ap", "no", "rejected")])
    owner.post(f"/api/workflows/{w['id']}/publish")
    ex = owner.post(f"/api/workflows/{w['id']}/run", json={"input": {}, "sync": True}).json()
    assert ex["status"] == "waiting_approval"
    ap = next(a for a in owner.get("/api/approvals").json() if a["source_id"] == ex["id"])
    owner.post(f"/api/approvals/{ap['id']}/decide", json={"decision": "approved"})
    run_jobs()
    ex = owner.get(f"/api/workflows/executions/{ex['id']}").json()
    assert ex["status"] == "succeeded"
    titles = [t["title"] for t in owner.get("/api/tasks").json()]
    assert "Payout approved" in titles and "Payout rejected" not in titles


def test_loop_branch_and_filter(client, owner):
    set_plan(owner.org_id, "professional")
    nodes = [N("t", "trigger.manual"), N("loop", "logic.loop", items="{{trigger.items}}"),
             N("each", "action.create_task", title="Item {{item}}"),
             N("br", "logic.branch", value="{{trigger.tier}}", cases="gold, silver"),
             N("gold", "action.create_task", title="Gold path"), N("f", "logic.filter", left="{{trigger.tier}}", operator="equals", right="never"),
             N("after", "action.create_task", title="Never runs")]
    edges = [E("t", "loop"), E("loop", "each", "each"), E("loop", "br", "done"), E("br", "gold", "gold"), E("br", "f", "default"), E("f", "after")]
    w = mk(owner, nodes, edges)
    assert owner.post(f"/api/workflows/{w['id']}/publish").status_code == 200, owner.post(f"/api/workflows/{w['id']}/validate").json()
    ex = owner.post(f"/api/workflows/{w['id']}/run", json={"input": {"items": ["a", "b", "c"], "tier": "gold"}, "sync": True}).json()
    assert ex["status"] == "succeeded", ex
    titles = [t["title"] for t in owner.get("/api/tasks").json()]
    assert {"Item a", "Item b", "Item c", "Gold path"} <= set(titles) and "Never runs" not in titles


def test_webhook_hmac_and_form(client, owner):
    set_plan(owner.org_id, "professional")
    w = mk(owner, [N("t", "trigger.webhook"), N("rec", "action.update_record", collection="events", data='{"kind": "{{trigger.kind}}"}')], [E("t", "rec")])
    pub = owner.post(f"/api/workflows/{w['id']}/publish").json()
    token = pub["webhook_url"].rsplit("/", 1)[-1]
    body = json.dumps({"kind": "signup"}).encode()
    assert client.post(f"/api/hooks/workflows/{token}", content=body).status_code == 401
    assert client.post(f"/api/hooks/workflows/{token}", content=body, headers={"X-Nexora-Signature": "sha256=deadbeef"}).status_code == 401
    sig = "sha256=" + hmac_sha256(pub["webhook_secret"], body)
    r = client.post(f"/api/hooks/workflows/{token}", content=body, headers={"X-Nexora-Signature": sig, "Content-Type": "application/json"})
    assert r.status_code == 202
    run_jobs()
    assert client.post("/api/hooks/workflows/unknown-token", content=body).status_code == 404
    f = mk(owner, [N("t", "trigger.form", title="Contact", fields="name, email"), N("task", "action.create_task", title="Lead {{trigger.name}}")], [E("t", "task")])
    fp = owner.post(f"/api/workflows/{f['id']}/publish").json()
    ftoken = fp["webhook_url"].rsplit("/", 1)[-1]
    assert client.get(f"/api/forms/{ftoken}").json()["fields"] == ["name", "email"]
    assert client.post(f"/api/forms/{ftoken}", json={"data": {"name": "Zoya", "email": "z@example.com", "extra": "ignored"}}).status_code == 201
    run_jobs()
    assert any(t["title"] == "Lead Zoya" for t in owner.get("/api/tasks").json())


def test_document_uploaded_trigger(client, owner):
    set_plan(owner.org_id, "professional")
    w = owner.post("/api/workflows/from-template/doc_summary_alert").json()
    owner.post(f"/api/workflows/{w['id']}/publish")
    from tests.fixtures import make_pdf
    owner.post("/api/documents", files={"file": ("contract.pdf", make_pdf(["Master services agreement. Payment terms are net 45 days from invoice."]), "application/pdf")})
    run_jobs()
    run_jobs()
    exs = owner.get(f"/api/workflows/{w['id']}/executions").json()
    assert exs and exs[0]["status"] == "succeeded", exs
    assert any(t["title"] == "Review: contract" for t in owner.get("/api/tasks").json())


def test_plan_gated_nodes(client, owner):
    set_plan(owner.org_id, "starter")
    w = mk(owner, [N("t", "trigger.manual"), N("h", "action.send_webhook", url="https://example.com")], [E("t", "h")])
    v = owner.post(f"/api/workflows/{w['id']}/validate").json()
    assert any("requires a plan" in e["message"] for e in v["errors"])
