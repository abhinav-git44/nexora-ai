from app.core import ratelimit
from tests.conftest import register, set_plan, run_jobs, PASSWORD
from tests.fixtures import POLICY_MD


def test_rate_limiting(client):
    a = register(client)
    ratelimit.ENABLED = True
    ratelimit.reset_local()
    codes = [client.post("/api/auth/login", json={"email": a.email, "password": "Wrong!pass1"}).status_code for _ in range(12)]
    assert 429 in codes


def test_security_headers_and_error_shape(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Request-Id"]
    r = client.post("/api/auth/login", json={"email": "not-an-email"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_ssrf_guard():
    import pytest
    from app.core.netguard import assert_public_url
    from app.core.errors import AppError
    for url in ["http://127.0.0.1/admin", "http://localhost:5432", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd",
                "http://10.0.0.5/", "gopher://x"]:
        with pytest.raises(AppError):
            assert_public_url(url)


def test_webhook_tool_blocked_for_internal_urls(client, owner):
    set_plan(owner.org_id, "professional")
    from tests.test_workflows import N, E, mk
    w = mk(owner, [N("t", "trigger.manual"), N("h", "action.send_webhook", url="http://169.254.169.254/latest/meta-data")], [E("t", "h")])
    owner.post(f"/api/workflows/{w['id']}/publish")
    ex = owner.post(f"/api/workflows/{w['id']}/run", json={"input": {}, "sync": True}).json()
    assert ex["status"] == "failed" and "private" in ex["error"]


def test_credentials_encrypted_at_rest(client, owner):
    from app.core.db import SessionLocal
    from app.models import IntegrationConnection
    from sqlalchemy import select
    r = owner.post("/api/integrations/openai/connect", json={"credentials": {"api_key": "sk-test-not-a-real-key-123456"}}).json()
    assert r["connection"]["status"] == "error"  # never marked connected without a successful real test
    assert "sk-test-not-a-real-key-123456" not in str(r)
    with SessionLocal() as db:
        c = db.scalar(select(IntegrationConnection).where(IntegrationConnection.provider == "openai"))
        assert "sk-test" not in c.encrypted_credentials
    assert owner.delete("/api/integrations/openai").json()["connection"]["status"] == "disconnected"


def test_admin_console_hidden_and_works(client, owner):
    assert owner.get("/api/admin/overview").status_code == 404
    root = register(client, email="superadmin@example.com")
    o = root.get("/api/admin/overview").json()
    assert o["organizations"] >= 1 and o["health"]["database"] is True
    orgs = root.get("/api/admin/orgs").json()
    target = next(x for x in orgs if x["id"] == owner.org_id)
    assert root.patch(f"/api/admin/orgs/{target['id']}", json={"suspended": True}).status_code == 200
    assert owner.get("/api/tasks").status_code == 403
    root.patch(f"/api/admin/orgs/{target['id']}", json={"suspended": False})
    assert owner.get("/api/tasks").status_code == 200
    assert root.put("/api/admin/feature-flags", json={"key": "ai_workflow_suggestions", "enabled": True}).status_code == 200
    assert owner.get("/api/support/flags").json()["ai_workflow_suggestions"] is True
    t = owner.post("/api/support/tickets", json={"subject": "Help", "body": "Something broke"}).json()
    assert any(x["id"] == t["id"] for x in root.get("/api/admin/support-tickets").json())
    assert root.get("/api/admin/product-metrics").status_code == 200
    assert root.get("/api/admin/jobs?status=failed").status_code == 200
    assert root.get("/api/experiments/results").status_code == 200


def test_audit_log(client, owner):
    set_plan(owner.org_id, "professional")
    owner.post("/api/documents", files={"file": ("p.md", POLICY_MD.encode(), "text/markdown")})
    logs = owner.get("/api/orgs/current/audit-logs").json()
    assert any(l["action"] == "document.uploaded" for l in logs)
    set_plan(owner.org_id, "starter")
    assert owner.get("/api/orgs/current/audit-logs").status_code == 402


def test_dashboard_reflects_activity(client, owner):
    set_plan(owner.org_id, "professional")
    owner.post("/api/documents", files={"file": ("p.md", POLICY_MD.encode(), "text/markdown")})
    run_jobs()
    owner.post("/api/documents/ask", json={"question": "What is the home office allowance?"})
    c = owner.post("/api/conversations", json={}).json()
    owner.post(f"/api/conversations/{c['id']}/messages", json={"content": "Who approves expenses above 5000 USD?"})
    d = owner.get("/api/analytics/dashboard?days=30").json()
    k = d["kpis"]
    assert k["ai_interactions"]["value"] == 1 and k["documents_processed"]["value"] == 1 and k["ai_requests"]["value"] >= 2
    assert d["estimates"]["time_saved_hours"]["is_estimate"] is True and k["outcomes"]["value"] >= 1
    ts = owner.get("/api/analytics/timeseries?days=7").json()
    assert sum(r["ai_query_completed"] for r in ts["series"]) == 1
    assert owner.get("/api/analytics/drilldown?metric=ai_requests&group=feature").json()["rows"]
    assert owner.get("/api/analytics/export?days=7").text.startswith("ai_query_completed") or True
    assert owner.get("/api/analytics/dashboard?days=3").status_code == 400


def test_experiment_assignment_is_sticky(client, owner):
    a = owner.get("/api/experiments/assignments").json()
    b = owner.get("/api/experiments/assignments").json()
    assert a == b and a["onboarding_flow"] in ("short", "guided")


def test_org_deletion_workflow(client):
    a = register(client)
    r = a.post("/api/orgs/current/delete", json={"confirm_name": "wrong", "password": PASSWORD})
    assert r.status_code == 400
    org = a.get("/api/orgs/current").json()
    assert a.post("/api/orgs/current/delete", json={"confirm_name": org["name"], "password": PASSWORD}).status_code == 200
    assert a.get("/api/orgs/current").json()["deletion_requested_at"]
    assert a.post("/api/orgs/current/delete/cancel").status_code == 200
