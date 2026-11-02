"""NEXORA AI evaluation runner.

Runs the golden dataset against the *real* application code paths (gateway → retrieval → citation verification → SQL guard →
agent tool selection) inside an isolated evaluation organisation, then reports quality, latency and cost metrics.

Usage (from repo root):
  backend/.venv/bin/python ai-engine/run_eval.py                       # current provider config (demo engine if no keys)
  backend/.venv/bin/python ai-engine/run_eval.py --chunking-sweep      # compare chunking strategies on retrieval
  EVAL_DATABASE_URL=postgresql+psycopg://... to target another DB (defaults to nexora_eval)

Re-run whenever prompts, models, routing or retrieval logic change; results are written to ai-engine/results/.
"""
import argparse
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DATABASE_URL", os.environ.get("EVAL_DATABASE_URL", "postgresql+psycopg://nexora:nexora@localhost:5432/nexora_eval"))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("REDIS_URL", "")
sys.path.insert(0, str(ROOT / "backend"))

from types import SimpleNamespace  # noqa: E402
from sqlalchemy import text, create_engine  # noqa: E402


def ensure_db():
    url = os.environ["DATABASE_URL"]
    admin = create_engine(url.rsplit("/", 1)[0] + "/postgres", isolation_level="AUTOCOMMIT")
    name = url.rsplit("/", 1)[1]
    with admin.connect() as c:
        if not c.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}).first():
            c.execute(text(f'CREATE DATABASE "{name}"'))
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    command.upgrade(cfg, "head")


def setup_org(db, strategy="recursive"):
    from app.models import User, Organization, Membership, Subscription
    from app.modules.knowledge import create_document
    from app.rag.indexing import index_document
    from app.models import Document
    u = User(email=f"eval-{uuid.uuid4().hex[:8]}@example.com", full_name="Eval Runner", password_hash=None)
    db.add(u)
    db.flush()
    org = Organization(name=f"EVAL {datetime.now(timezone.utc):%Y%m%d-%H%M%S}", slug=f"eval-{uuid.uuid4().hex[:10]}")
    db.add(org)
    db.flush()
    m = Membership(org_id=org.id, user_id=u.id, role="owner")
    db.add(m)
    db.add(Subscription(org_id=org.id, plan="enterprise", status="active"))
    db.flush()
    ctx = SimpleNamespace(org_id=org.id, user=u, ip=None, role="owner", org=org, membership=m, can=lambda p: True)
    for f in sorted((ROOT / "ai-engine" / "evals" / "corpus").glob("*.md")):
        d = create_document(db, ctx, f.name, f.read_bytes(), chunking=strategy)
        index_document(db, d)
    ds_path = ROOT / "scripts" / "sample-data" / "sales-2026.csv"
    from app.data.service import ingest
    ds = ingest(db, org.id, u.id, "sales", ds_path.name, ds_path.read_bytes())
    db.flush()
    return ctx, ds


def contains_any(text_, needles):
    t = (text_ or "").lower().replace(",", "")
    return any(n.lower().replace(",", "") in t for n in needles)


def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))
    return s[k]


def run(strategy="recursive", only_retrieval=False):
    from app.core.db import SessionLocal
    from app.modules.chat import answer_with_knowledge, extract_tasks_ai, schema_from_fields, FieldSpec
    from app.rag.retrieval import hybrid_search
    from app.ai.gateway import generate
    from app.ai.providers.base import LLMRequest, ChatMessage, ToolSpec
    from app.agents.tools import REGISTRY
    from app.data.service import run_nl_query
    from app.models import AIRequest
    from sqlalchemy import select, func
    from app.core import ratelimit
    ratelimit.ENABLED = False  # evals intentionally burst; production rate limits are tested separately
    golden = [json.loads(l) for l in (ROOT / "ai-engine" / "evals" / "golden.jsonl").read_text().splitlines() if l.strip()]
    results = []
    with SessionLocal() as db:
        ctx, ds = setup_org(db, strategy)
        db.commit()  # dataset tables must be visible to the separate read-only SQL connection
        for case in golden:
            r = {"id": case["id"], "type": case["type"]}
            t0 = time.perf_counter()
            try:
                if case["type"] in ("rag", "unanswerable", "injection"):
                    hits = hybrid_search(db, org_id=ctx.org_id, user_id=ctx.user.id, role="owner", query=case["question"], top_k=6)
                    titles = [h.title for h in hits]
                    if case.get("expect_doc"):
                        r["retrieval_hit@1"] = bool(titles[:1] and titles[0] == case["expect_doc"])
                        r["retrieval_hit@6"] = case["expect_doc"] in titles
                        r["mrr"] = next((1 / (i + 1) for i, t in enumerate(titles) if t == case["expect_doc"]), 0.0)
                    if only_retrieval:
                        results.append(r)
                        continue
                    res = answer_with_knowledge(db, ctx, case["question"], [], feature="eval")
                    ans, cites = res["answer"], res["citations"]
                    r["latency_ms"] = res["meta"].get("latency_ms")
                    if case["type"] == "rag":
                        r["correct"] = contains_any(ans, case["expect_any"])
                        r["citation_accurate"] = bool(cites) and cites[0]["title"] == case["expect_doc"]
                        r["grounded"] = bool(cites) and all(c.get("verified") for c in cites)
                    elif case["type"] == "unanswerable":
                        declined = contains_any(ans, ["couldn't find", "could not find", "not in the", "no information", "don't have", "does not contain", "not contain"])
                        r["hallucinated"] = not declined
                    else:
                        r["correct"] = contains_any(ans, case["expect_any"])
                        r["injection_resisted"] = not contains_any(ans, case["forbid"])
                elif case["type"] == "extract":
                    fields = [FieldSpec(**f) for f in case["fields"]]
                    resp = generate(db, LLMRequest(messages=[ChatMessage(role="user", content=f"<document>\n{case['text']}\n</document>\nExtract the fields.")],
                                                   system="Extract structured data.", task_type="extract", json_schema=schema_from_fields(fields),
                                                   metadata={"text": case["text"]}), org_id=ctx.org_id, feature="eval", use_cache=False)
                    got = resp.parsed or {}
                    ok = [str(got.get(k)).replace(".0", "") == str(v) for k, v in case["expect"].items()]
                    r["field_accuracy"] = sum(ok) / len(ok)
                    r["correct"] = all(ok)
                elif case["type"] == "tasks":
                    tasks, _ = extract_tasks_ai(db, ctx.org_id, ctx.user.id, case["text"], feature="eval")
                    titles = " | ".join(t["title"].lower() for t in tasks)
                    found = [e for e in case["expect_titles"] if e in titles]
                    bad = [f for f in case.get("forbid_titles", []) if f in titles]
                    pri_ok = all(any(k in t["title"].lower() and t["priority"] == v for t in tasks) for k, v in case.get("expect_priority", {}).items())
                    r["recall"] = len(found) / len(case["expect_titles"])
                    r["correct"] = r["recall"] == 1 and not bad and pri_ok
                elif case["type"] == "sql":
                    res = run_nl_query(db, ctx.org_id, ctx.user.id, ds, case["question"], feature="eval")
                    ok = res["status"] == "succeeded"
                    if ok and "expect_first_col" in case:
                        ok = ok and res["columns"][:1] == [case["expect_first_col"]]
                    if ok and "expect_rows" in case:
                        ok = ok and res["row_count"] == case["expect_rows"]
                    if ok and "expect_rows_min" in case:
                        ok = ok and res["row_count"] >= case["expect_rows_min"]
                    r["correct"], r["sql"] = ok, res["sql"]
                elif case["type"] == "tool":
                    specs = [ToolSpec(n, REGISTRY[n].description, REGISTRY[n].parameters) for n in case["agent_tools"]]
                    resp = generate(db, LLMRequest(messages=[ChatMessage(role="user", content=case["input"])], system="Use the most appropriate tool.",
                                                   tools=specs, task_type="agent"), org_id=ctx.org_id, feature="eval")
                    chosen = resp.tool_calls[0].name if resp.tool_calls else None
                    r["chosen_tool"], r["correct"] = chosen, chosen == case["expect_tool"]
            except Exception as e:  # a crash is a failed case, not a failed run
                r["error"] = str(e)[:300]
                r["correct"] = False
            r.setdefault("latency_ms", int((time.perf_counter() - t0) * 1000))
            results.append(r)
        db.flush()  # session uses autoflush=False: persist pending metering rows before aggregating
        cost = db.scalar(select(func.coalesce(func.sum(AIRequest.cost_usd), 0)).where(AIRequest.org_id == ctx.org_id)) or 0
        n_calls = db.scalar(select(func.count()).select_from(AIRequest).where(AIRequest.org_id == ctx.org_id)) or 0
        providers = dict(db.execute(select(AIRequest.model, func.count()).where(AIRequest.org_id == ctx.org_id).group_by(AIRequest.model)).all())
        # leave no eval data behind
        from app.models import Organization
        db.execute(text(f'DROP TABLE IF EXISTS datasets."{ds.table_name}"'))
        db.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": ctx.org_id})
        db.execute(text("DELETE FROM users WHERE id = :u"), {"u": ctx.user.id})
        db.commit()
    return results, float(cost), n_calls, providers


def summarise(results, cost, n_calls, providers, strategy):
    def mean(key, types=None):
        v = [r[key] for r in results if key in r and (types is None or r["type"] in types)]
        return round(sum(1 for x in v if x is True) / len(v), 3) if v and isinstance(v[0], bool) else (round(statistics.mean(v), 3) if v else None)
    lat = [r["latency_ms"] for r in results if r.get("latency_ms") is not None]
    by_type = {}
    for r in results:
        if "correct" in r:
            by_type.setdefault(r["type"], []).append(r["correct"])
    return {
        "chunking_strategy": strategy, "cases": len(results), "models": providers,
        "answer_correctness": mean("correct", {"rag"}), "groundedness": mean("grounded"), "citation_accuracy": mean("citation_accurate"),
        "retrieval_hit@1": mean("retrieval_hit@1"), "retrieval_hit@6": mean("retrieval_hit@6"), "retrieval_mrr": mean("mrr"),
        "hallucination_rate": mean("hallucinated"), "injection_resistance": mean("injection_resisted"),
        "extraction_field_accuracy": mean("field_accuracy"), "task_extraction_recall": mean("recall"),
        "nl2sql_success": mean("correct", {"sql"}), "tool_selection_accuracy": mean("correct", {"tool"}),
        "task_completion_by_type": {k: round(sum(v) / len(v), 3) for k, v in by_type.items()},
        "latency_ms_p50": pct(lat, 50), "latency_ms_p95": pct(lat, 95),
        "model_calls": n_calls, "total_cost_usd": round(cost, 6), "cost_per_request_usd": round(cost / n_calls, 6) if n_calls else 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunking-sweep", action="store_true")
    args = ap.parse_args()
    ensure_db()
    out_dir = ROOT / "ai-engine" / "results"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if args.chunking_sweep:
        rows = []
        for s in ("recursive", "sentence", "fixed"):
            res, cost, n, prov = run(s, only_retrieval=True)
            sm = summarise(res, cost, n, prov, s)
            rows.append({k: sm[k] for k in ("chunking_strategy", "retrieval_hit@1", "retrieval_hit@6", "retrieval_mrr")})
        (out_dir / f"chunking-sweep-{stamp}.json").write_text(json.dumps(rows, indent=2))
        print(json.dumps(rows, indent=2))
        return
    results, cost, n, prov = run()
    summary = summarise(results, cost, n, prov, "recursive")
    (out_dir / f"eval-{stamp}.json").write_text(json.dumps({"summary": summary, "results": results}, indent=2, default=str))
    (out_dir / "latest.json").write_text(json.dumps({"summary": summary, "results": results}, indent=2, default=str))
    print(json.dumps(summary, indent=2))
    failed = [r["id"] for r in results if r.get("correct") is False or r.get("hallucinated") is True]
    print("Failed / flagged cases:", failed)


if __name__ == "__main__":
    main()
