import pytest
from tests.conftest import set_plan
from tests.fixtures import SALES_CSV, make_xlsx
from app.data.sqlguard import validate_and_rewrite, UnsafeSQL

COLS = {"order_id", "order_date", "customer", "product", "category", "quantity", "revenue", "region"}


@pytest.mark.parametrize("sql", [
    "DROP TABLE data", "DELETE FROM data", "UPDATE data SET revenue = 0", "INSERT INTO data VALUES (1)",
    "SELECT * FROM data; DROP TABLE users", "SELECT * FROM users", "SELECT * FROM public.users", "SELECT * FROM information_schema.tables",
    "SELECT pg_sleep(10)", "SELECT * FROM data -- comment", "SELECT * FROM data /* x */", "SELECT * FROM data UNION SELECT * FROM users",
    "SELECT password_hash FROM data", "COPY data TO '/tmp/x'", "SELECT * INTO newtable FROM data", "WITH x AS (DELETE FROM data RETURNING *) SELECT * FROM x",
    "SELECT current_setting('server_version')", "SELECT * FROM data FOR UPDATE", "CREATE TABLE t (a int)", "GRANT ALL ON data TO public",
])
def test_sqlguard_rejects(sql):
    with pytest.raises(UnsafeSQL):
        validate_and_rewrite(sql, "ds_abc", COLS)


def test_sqlguard_rewrites_and_limits():
    out = validate_and_rewrite('SELECT "customer", SUM("revenue") AS total FROM data GROUP BY 1 ORDER BY 2 DESC', "ds_abc", COLS)
    assert 'datasets.ds_abc' in out and "LIMIT 1000" in out
    out = validate_and_rewrite("SELECT * FROM data LIMIT 999999", "ds_abc", COLS)
    assert "LIMIT 1000" in out
    out = validate_and_rewrite("WITH m AS (SELECT customer, revenue FROM data) SELECT customer FROM m", "ds_abc", COLS)
    assert "datasets.ds_abc" in out


def test_ingest_profile_and_nl_queries(client, owner):
    set_plan(owner.org_id, "professional")
    d = owner.post("/api/datasets", files={"file": ("sales.csv", SALES_CSV.encode(), "text/csv")}).json()
    cols = {c["name"]: c for c in d["columns"]}
    assert cols["revenue"]["type"] == "numeric" and cols["revenue"]["kind"] == "measure"
    assert cols["order_date"]["type"] == "date" and cols["customer"]["kind"] == "dimension"
    assert d["row_count"] == 10
    assert any("casing" in r["issue"] for r in d["recommendations"])  # "hardware" vs "Hardware"
    r = owner.post(f"/api/datasets/{d['id']}/query", json={"question": "Which customers generated the most revenue?"}).json()
    assert r["status"] == "succeeded", r
    assert r["rows"][0][0] == "Deccan Labs" and r["chart"]["type"] == "bar"
    r = owner.post(f"/api/datasets/{d['id']}/query", json={"question": "What is the monthly revenue trend?"}).json()
    assert r["status"] == "succeeded" and len(r["rows"]) == 3 and r["chart"]["type"] == "line"
    r = owner.post(f"/api/datasets/{d['id']}/query", json={"question": "top 2 products by revenue"}).json()
    assert len(r["rows"]) == 2
    bad = owner.post(f"/api/datasets/{d['id']}/sql", json={"sql": "DELETE FROM data"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "unsafe_sql"
    ok = owner.post(f"/api/datasets/{d['id']}/sql", json={"sql": 'SELECT "region", COUNT(*) AS n FROM data GROUP BY 1'}).json()
    assert ok["row_count"] == 4
    csv_ = owner.get(f"/api/datasets/queries/{r['id']}/export?format=csv")
    assert csv_.status_code == 200 and csv_.text.startswith("product")
    xl = owner.get(f"/api/datasets/queries/{r['id']}/export?format=xlsx")
    assert xl.status_code == 200 and xl.content[:2] == b"PK"
    rep = owner.post(f"/api/datasets/{d['id']}/report").json()
    assert rep["report"]
    assert owner.get(f"/api/datasets/{d['id']}/preview").json()["rows"]


def test_xlsx_and_feature_gate(client, owner):
    set_plan(owner.org_id, "free")
    r = owner.post("/api/datasets", files={"file": ("s.csv", SALES_CSV.encode(), "text/csv")})
    assert r.status_code == 402
    set_plan(owner.org_id, "professional")
    x = make_xlsx([["Team", "Tickets Closed", "Week"], ["Support", 40, "2026-10-05"], ["Support", 55, "2026-10-12"], ["Sales", 12, "2026-10-05"]])
    d = owner.post("/api/datasets", files={"file": ("ops.xlsx", x, "application/octet-stream")}).json()
    assert {c["name"] for c in d["columns"]} == {"team", "tickets_closed", "week"}
    r = owner.post(f"/api/datasets/{d['id']}/query", json={"question": "total tickets closed by team"}).json()
    assert r["status"] == "succeeded" and r["rows"][0] == ["Support", 95]


def test_csv_injection_escaped(client, owner):
    set_plan(owner.org_id, "professional")
    evil = "name,amount\n=HYPERLINK(\"http://evil\"),5\nok,7\n"
    d = owner.post("/api/datasets", files={"file": ("e.csv", evil.encode(), "text/csv")}).json()
    r = owner.post(f"/api/datasets/{d['id']}/sql", json={"sql": "SELECT name FROM data"}).json()
    out = owner.get(f"/api/datasets/queries/{r['id']}/export?format=csv").text
    assert "'=HYPERLINK" in out
