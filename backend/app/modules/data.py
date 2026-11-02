"""Module 6: Business Data Intelligence."""
import csv
import io
import uuid
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.core.audit import audit_ctx, track, outcome
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import OrgContext, require
from app.core.errors import not_found, bad_request, AppError
from app.core.plans import check_limit, require_feature, increment_usage
from app.data.service import ingest, run_nl_query, execute_safe
from app.data.sqlguard import UnsafeSQL
from app.models import Dataset, DatasetQuery
from app.modules.common import iso

router = APIRouter(prefix="/api/datasets", tags=["data"])
settings = get_settings()


def ds_out(d: Dataset, full: bool = False) -> dict:
    out = {"id": str(d.id), "name": d.name, "filename": d.filename, "row_count": d.row_count, "columns": d.columns,
           "status": d.status, "created_at": iso(d.created_at), "recommendation_count": len(d.recommendations or [])}
    if full:
        out.update({"profile": d.profile, "recommendations": d.recommendations})
    return out


def get_ds(db, ctx, ds_id) -> Dataset:
    d = db.get(Dataset, ds_id)
    if not d or d.org_id != ctx.org_id:
        raise not_found("Dataset")
    return d


@router.get("")
def list_datasets(ctx: OrgContext = Depends(require("datasets.read")), db: Session = Depends(get_db)):
    return [ds_out(d) for d in db.scalars(select(Dataset).where(Dataset.org_id == ctx.org_id).order_by(Dataset.created_at.desc()))]


@router.post("", status_code=201)
async def upload(file: UploadFile = File(...), name: str | None = Form(None), ctx: OrgContext = Depends(require("datasets.write")),
                 db: Session = Depends(get_db)):
    require_feature(db, ctx.org_id, "data_intelligence")
    check_limit(db, ctx.org_id, "datasets")
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise bad_request(f"File exceeds {settings.max_upload_mb} MB")
    fn = file.filename or "data.csv"
    d = ingest(db, ctx.org_id, ctx.user.id, name or fn.rsplit(".", 1)[0], fn, data)
    audit_ctx(db, ctx, "dataset.uploaded", "dataset", d.id, {"rows": d.row_count})
    track(db, "dataset_uploaded", org_id=ctx.org_id, user_id=ctx.user.id, properties={"rows": d.row_count, "columns": len(d.columns)})
    return ds_out(d, True)


@router.get("/{ds_id}")
def get_dataset(ds_id: uuid.UUID, ctx: OrgContext = Depends(require("datasets.read")), db: Session = Depends(get_db)):
    return ds_out(get_ds(db, ctx, ds_id), True)


@router.get("/{ds_id}/preview")
def preview(ds_id: uuid.UUID, ctx: OrgContext = Depends(require("datasets.read")), db: Session = Depends(get_db)):
    d = get_ds(db, ctx, ds_id)
    cols, rows, _ = execute_safe(db, d, "SELECT * FROM data LIMIT 50")
    return {"columns": cols, "rows": rows}


@router.delete("/{ds_id}")
def delete_dataset(ds_id: uuid.UUID, ctx: OrgContext = Depends(require("datasets.write")), db: Session = Depends(get_db)):
    d = get_ds(db, ctx, ds_id)
    db.execute(text(f'DROP TABLE IF EXISTS datasets."{d.table_name}"'))
    audit_ctx(db, ctx, "dataset.deleted", "dataset", d.id, {"name": d.name})
    db.delete(d)
    return {"ok": True}


class QueryIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


@router.post("/{ds_id}/query")
def nl_query(ds_id: uuid.UUID, body: QueryIn, ctx: OrgContext = Depends(require("datasets.read")), db: Session = Depends(get_db)):
    require_feature(db, ctx.org_id, "data_intelligence")
    check_limit(db, ctx.org_id, "ai_messages")
    d = get_ds(db, ctx, ds_id)
    res = run_nl_query(db, ctx.org_id, ctx.user.id, d, body.question)
    increment_usage(db, ctx.org_id, "ai_messages")
    track(db, "dataset_queried", org_id=ctx.org_id, user_id=ctx.user.id, properties={"status": res["status"], "rows": res["row_count"]})
    if res["status"] == "succeeded":
        outcome(db, "data_question_answered", org_id=ctx.org_id, user_id=ctx.user.id)
    return res


class SQLIn(BaseModel):
    sql: str = Field(min_length=6, max_length=5000)


@router.post("/{ds_id}/sql")
def run_sql(ds_id: uuid.UUID, body: SQLIn, ctx: OrgContext = Depends(require("datasets.read")), db: Session = Depends(get_db)):
    """Lets analysts edit the generated SQL. The same guard applies to human-written SQL."""
    require_feature(db, ctx.org_id, "data_intelligence")
    d = get_ds(db, ctx, ds_id)
    try:
        cols, rows, safe = execute_safe(db, d, body.sql)
    except UnsafeSQL as e:
        raise bad_request(str(e), "unsafe_sql")
    except Exception as e:
        raise bad_request(str(getattr(e, "orig", e)).splitlines()[0][:300], "sql_error")
    from app.data.service import auto_chart
    q = DatasetQuery(org_id=ctx.org_id, dataset_id=d.id, user_id=ctx.user.id, question="(manual SQL)", generated_sql=body.sql, executed_sql=safe,
                     status="succeeded", row_count=len(rows), chart=auto_chart(cols, rows, None))
    db.add(q)
    db.flush()
    return {"id": str(q.id), "sql": safe, "columns": cols, "rows": rows, "row_count": len(rows), "chart": q.chart, "status": "succeeded"}


@router.get("/{ds_id}/queries")
def history(ds_id: uuid.UUID, ctx: OrgContext = Depends(require("datasets.read")), db: Session = Depends(get_db)):
    d = get_ds(db, ctx, ds_id)
    rows = db.scalars(select(DatasetQuery).where(DatasetQuery.dataset_id == d.id, DatasetQuery.org_id == ctx.org_id)
                      .order_by(DatasetQuery.created_at.desc()).limit(50)).all()
    return [{"id": str(q.id), "question": q.question, "sql": q.executed_sql or q.generated_sql, "status": q.status, "error": q.error,
             "row_count": q.row_count, "created_at": iso(q.created_at)} for q in rows]


@router.get("/queries/{query_id}/export")
def export(query_id: uuid.UUID, format: str = "csv", ctx: OrgContext = Depends(require("datasets.read")), db: Session = Depends(get_db)):
    q = db.get(DatasetQuery, query_id)
    if not q or q.org_id != ctx.org_id or not q.executed_sql:
        raise not_found("Query")
    d = db.get(Dataset, q.dataset_id)
    cols, rows, _ = execute_safe(db, d, q.generated_sql)
    track(db, "response_exported", org_id=ctx.org_id, user_id=ctx.user.id, properties={"format": format, "source": "dataset"})
    if format == "xlsx":
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Results"
        ws.append(cols)
        for r in rows:
            ws.append(r)
        ws2 = wb.create_sheet("Query")
        ws2.append(["Question", q.question])
        ws2.append(["SQL", q.executed_sql])
        buf = io.BytesIO()
        wb.save(buf)
        return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="query-{q.id.hex[:8]}.xlsx"'})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        w.writerow(["" if v is None else ("'" + v if isinstance(v, str) and v[:1] in "=+-@" else v) for v in r])  # CSV-injection safe
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="query-{q.id.hex[:8]}.csv"'})


@router.post("/{ds_id}/report")
def report(ds_id: uuid.UUID, ctx: OrgContext = Depends(require("datasets.read")), db: Session = Depends(get_db)):
    require_feature(db, ctx.org_id, "data_intelligence")
    check_limit(db, ctx.org_id, "ai_messages")
    d = get_ds(db, ctx, ds_id)
    from app.ai.gateway import generate
    from app.ai.providers.base import LLMRequest, ChatMessage
    import json
    qs = db.scalars(select(DatasetQuery).where(DatasetQuery.dataset_id == d.id, DatasetQuery.status == "succeeded")
                    .order_by(DatasetQuery.created_at.desc()).limit(5)).all()
    findings = []
    for q in qs:
        try:
            cols, rows, _ = execute_safe(db, d, q.generated_sql)
            findings.append({"question": q.question, "columns": cols, "rows": rows[:15]})
        except Exception:
            continue
    material = json.dumps({"dataset": d.name, "rows": d.row_count, "columns": d.columns, "profile": d.profile,
                           "data_quality_issues": d.recommendations, "query_results": findings}, default=str)[:30000]
    r = generate(db, LLMRequest(messages=[ChatMessage(role="user", content=f"Data:\n{material}\n\nWrite a data analysis report: overview, key findings with numbers "
                                                         "from the query results only, data-quality caveats, recommended next questions.")],
                                system="You are a careful business data analyst. Use only numbers present in the provided material.", task_type="analysis",
                                metadata={"demo_handler": "report", "text": material}), org_id=ctx.org_id, user_id=ctx.user.id, feature="data")
    increment_usage(db, ctx.org_id, "ai_messages")
    track(db, "report_generated", org_id=ctx.org_id, user_id=ctx.user.id, properties={"source": "dataset"})
    outcome(db, "report_generated", org_id=ctx.org_id, user_id=ctx.user.id)
    return {"report": r.text, "model": r.model, "demo": r.demo}


@router.get("/{ds_id}/powerbi")
def powerbi(ds_id: uuid.UUID, ctx: OrgContext = Depends(require("datasets.read")), db: Session = Depends(get_db)):
    d = get_ds(db, ctx, ds_id)
    return {"connector": "PostgreSQL database (Power BI Desktop → Get Data → PostgreSQL)",
            "server": "<your database host>:5432", "database": "<database name>", "schema": "datasets", "table": d.table_name,
            "role": "nexora_readonly (SELECT-only; see deployment/sql/readonly_role.sql)",
            "notes": "Use DirectQuery for live data or Import for scheduled refresh. Organisation-level product analytics are available in the "
                     "analytics.* views (database/analytics_views.sql)."}
