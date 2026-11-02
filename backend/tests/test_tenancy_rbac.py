"""Tenant isolation and role-based access control: the highest-risk area of a multi-tenant SaaS."""
from tests.conftest import register, add_member, set_plan, run_jobs
from tests.fixtures import POLICY_MD, SALES_CSV


def _seed(owner):
    set_plan(owner.org_id, "professional")
    doc = owner.post("/api/documents", files={"file": ("policy.md", POLICY_MD.encode(), "text/markdown")}).json()
    run_jobs()
    conv = owner.post("/api/conversations", json={}).json()
    agent = owner.post("/api/agents/from-template/project_management").json()
    wf = owner.post("/api/workflows/from-template/doc_summary_alert").json()
    task = owner.post("/api/tasks", json={"title": "Secret task"}).json()
    ds = owner.post("/api/datasets", files={"file": ("sales.csv", SALES_CSV.encode(), "text/csv")}).json()
    return {"doc": doc["id"], "conv": conv["id"], "agent": agent["id"], "wf": wf["id"], "task": task["id"], "ds": ds["id"]}


def test_cross_tenant_access_is_404(client, owner, other_org):
    ids = _seed(owner)
    set_plan(other_org.org_id, "professional")
    for url in [f"/api/documents/{ids['doc']}", f"/api/documents/{ids['doc']}/chunks", f"/api/conversations/{ids['conv']}",
                f"/api/agents/{ids['agent']}", f"/api/workflows/{ids['wf']}", f"/api/tasks/{ids['task']}", f"/api/datasets/{ids['ds']}",
                f"/api/datasets/{ids['ds']}/preview"]:
        assert other_org.get(url).status_code == 404, url
    assert other_org.post(f"/api/agents/{ids['agent']}/runs", json={"input": "hi"}).status_code == 404
    assert other_org.delete(f"/api/documents/{ids['doc']}").status_code == 404
    assert other_org.patch(f"/api/tasks/{ids['task']}", json={"title": "pwned"}).status_code == 404
    assert other_org.post(f"/api/datasets/{ids['ds']}/query", json={"question": "total revenue"}).status_code == 404
    # lists never include the other tenant's rows
    assert all(t["title"] != "Secret task" for t in other_org.get("/api/tasks").json())
    assert other_org.get("/api/documents").json() == []


def test_org_header_spoofing(client, owner, other_org):
    spoof = {"Authorization": f"Bearer {other_org.token}", "X-Org-Id": owner.org_id}
    assert client.get("/api/tasks", headers=spoof).status_code == 404
    assert client.get("/api/orgs/current", headers=spoof).status_code == 404
    assert client.get("/api/tasks", headers={"Authorization": f"Bearer {other_org.token}"}).status_code == 400  # header required
    assert client.get("/api/tasks", headers={"Authorization": f"Bearer {other_org.token}", "X-Org-Id": "not-a-uuid"}).status_code == 400


def test_rag_never_retrieves_other_tenant(client, owner, other_org):
    _seed(owner)
    res = other_org.post("/api/documents/search", json={"query": "CFO approval expenses above 5000"}).json()
    assert res == []
    ans = other_org.post("/api/documents/ask", json={"question": "Who approves expenses above 5000 USD?"}).json()
    assert ans["citations"] == []
    mine = owner.post("/api/documents/search", json={"query": "CFO approval expenses above 5000"}).json()
    assert mine and mine[0]["title"] == "policy"


def test_role_permissions(client, owner):
    set_plan(owner.org_id, "professional")
    viewer = add_member(owner, "viewer")
    member = add_member(owner, "member")
    manager = add_member(owner, "manager")
    admin = add_member(owner, "admin")
    # viewer: read-only
    assert viewer.get("/api/tasks").status_code == 200
    assert viewer.post("/api/tasks", json={"title": "x"}).status_code == 403
    assert viewer.post("/api/conversations", json={}).status_code == 403
    # member: can work, cannot build agents/workflows or manage team
    assert member.post("/api/tasks", json={"title": "x"}).status_code == 201
    assert member.post("/api/agents/from-template/operations").status_code == 403
    assert member.post("/api/workflows", json={"name": "w"}).status_code == 403
    assert member.post("/api/orgs/current/invitations", json={"email": "z@example.com", "role": "member"}).status_code == 403
    assert member.get("/api/analytics/dashboard").status_code == 403
    # manager: builds agents/workflows, cannot see billing
    assert manager.post("/api/agents/from-template/operations").status_code == 201
    assert manager.get("/api/billing/subscription").status_code == 403
    # admin: manages members but cannot touch the owner or grant owner
    members = admin.get("/api/orgs/current/members").json()
    owner_m = next(m for m in members if m["role"] == "owner")
    assert admin.patch(f"/api/orgs/current/members/{owner_m['id']}", json={"role": "member"}).status_code == 403
    viewer_m = next(m for m in members if m["role"] == "viewer")
    assert admin.patch(f"/api/orgs/current/members/{viewer_m['id']}", json={"role": "owner"}).status_code == 403
    assert admin.patch(f"/api/orgs/current/members/{viewer_m['id']}", json={"role": "member"}).status_code == 200
    # billing.manage is owner-only
    assert admin.post("/api/billing/change-plan", json={"plan": "starter"}).status_code == 403


def test_deactivated_member_loses_access(client, owner):
    m = add_member(owner, "member")
    mem = next(x for x in owner.get("/api/orgs/current/members").json() if x["user"]["email"] == m.email)
    assert owner.post(f"/api/orgs/current/members/{mem['id']}/deactivate").status_code == 200
    assert m.get("/api/tasks").status_code == 404
    assert owner.post(f"/api/orgs/current/members/{mem['id']}/reactivate").status_code == 200
    assert m.get("/api/tasks").status_code == 200


def test_last_owner_protection_and_invites(client, owner):
    members = owner.get("/api/orgs/current/members").json()
    me = members[0]
    assert owner.patch(f"/api/orgs/current/members/{me['id']}", json={"role": "admin"}).status_code == 400  # self-change blocked
    assert owner.post("/api/orgs/current/leave").status_code == 400
    # unverified owner cannot invite
    fresh = register(client)
    r = fresh.post("/api/orgs/current/invitations", json={"email": "a@example.com", "role": "member"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_unverified"


def test_document_role_restriction(client, owner):
    set_plan(owner.org_id, "professional")
    member = add_member(owner, "member")
    owner.post("/api/documents", data={"min_role": "manager"},
               files={"file": ("salaries.txt", b"Executive compensation bands: the CEO salary band is confidential and set by the board.", "text/plain")})
    run_jobs()
    assert member.get("/api/documents").json() == []
    assert member.post("/api/documents/search", json={"query": "CEO salary band"}).json() == []
    assert owner.post("/api/documents/search", json={"query": "CEO salary band"}).json()
