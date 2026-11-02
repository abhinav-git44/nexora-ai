"""Module 5: visual workflow automation API."""
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.audit import audit_ctx, track
from app.core.config import get_settings
from app.core.crypto import decrypt_str
from app.core.db import get_db
from app.core.deps import OrgContext, require
from app.core.errors import not_found, bad_request
from app.core.plans import check_limit
from app.models import Workflow, WorkflowVersion, WorkflowExecution, WorkflowExecutionLog
from app.modules.common import iso
from app.workflows.nodes import node_catalog
from app.workflows.service import validate_definition, publish, create_execution, org_features
from app.workflows.templates import WORKFLOW_TEMPLATES

router = APIRouter(prefix="/api/workflows", tags=["workflows"])
settings = get_settings()


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    definition: dict | None = None


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    definition: dict | None = None


def wf_out(w: Workflow, ctx: OrgContext | None = None, detail: bool = False) -> dict:
    d = {"id": str(w.id), "name": w.name, "description": w.description, "status": w.status, "published_version": w.published_version,
         "trigger_type": w.trigger_type, "schedule_cron": w.schedule_cron, "next_run_at": iso(w.next_run_at),
         "created_at": iso(w.created_at), "updated_at": iso(w.updated_at)}
    if detail:
        d["definition"] = w.draft_definition
        if w.webhook_token:
            d["webhook_url"] = f"{settings.api_base_url}/api/hooks/workflows/{w.webhook_token}"
            d["form_url"] = f"{settings.app_base_url}/forms/{w.webhook_token}" if w.trigger_type == "form" else None
        if w.webhook_secret_enc and ctx and ctx.can("workflows.write"):
            d["webhook_secret"] = decrypt_str(w.webhook_secret_enc)
    return d


def get_wf(db, ctx, wf_id) -> Workflow:
    w = db.get(Workflow, wf_id)
    if not w or w.org_id != ctx.org_id:
        raise not_found("Workflow")
    return w


EMPTY = {"nodes": [{"id": "trigger", "type": "trigger.manual", "position": {"x": 80, "y": 160}, "data": {"label": "Manual trigger", "config": {}}}],
         "edges": []}


@router.get("/nodes")
def nodes(ctx: OrgContext = Depends(require("workflows.read"))):
    return node_catalog()


@router.get("/templates")
def templates(ctx: OrgContext = Depends(require("workflows.read"))):
    return [{"key": k, "name": v["name"], "description": v["description"], "definition": v["definition"]} for k, v in WORKFLOW_TEMPLATES.items()]


@router.get("")
def list_workflows(ctx: OrgContext = Depends(require("workflows.read")), db: Session = Depends(get_db)):
    wfs = db.scalars(select(Workflow).where(Workflow.org_id == ctx.org_id, Workflow.status != "archived").order_by(Workflow.updated_at.desc())).all()
    stats = {r[0]: r for r in db.execute(
        select(WorkflowExecution.workflow_id, func.count(), func.count().filter(WorkflowExecution.status == "succeeded"),
               func.count().filter(WorkflowExecution.status == "failed"), func.max(WorkflowExecution.created_at))
        .where(WorkflowExecution.org_id == ctx.org_id).group_by(WorkflowExecution.workflow_id))}
    out = []
    for w in wfs:
        s = stats.get(w.id)
        out.append({**wf_out(w), "executions": s[1] if s else 0, "succeeded": s[2] if s else 0, "failed": s[3] if s else 0,
                    "last_run_at": iso(s[4]) if s else None})
    return out


@router.post("", status_code=201)
def create_workflow(body: WorkflowIn, ctx: OrgContext = Depends(require("workflows.write")), db: Session = Depends(get_db)):
    check_limit(db, ctx.org_id, "workflows")
    w = Workflow(org_id=ctx.org_id, name=body.name, description=body.description, draft_definition=body.definition or EMPTY, created_by=ctx.user.id)
    db.add(w)
    db.flush()
    audit_ctx(db, ctx, "workflow.created", "workflow", w.id)
    track(db, "workflow_created", org_id=ctx.org_id, user_id=ctx.user.id)
    return wf_out(w, ctx, True)


@router.post("/from-template/{key}", status_code=201)
def from_template(key: str, ctx: OrgContext = Depends(require("workflows.write")), db: Session = Depends(get_db)):
    t = WORKFLOW_TEMPLATES.get(key)
    if not t:
        raise not_found("Template")
    return create_workflow(WorkflowIn(name=t["name"], description=t["description"], definition=t["definition"]), ctx, db)


@router.get("/{wf_id}")
def get_workflow(wf_id: uuid.UUID, ctx: OrgContext = Depends(require("workflows.read")), db: Session = Depends(get_db)):
    w = get_wf(db, ctx, wf_id)
    versions = db.scalars(select(WorkflowVersion).where(WorkflowVersion.workflow_id == w.id).order_by(WorkflowVersion.version.desc())).all()
    return {**wf_out(w, ctx, True), "versions": [{"version": v.version, "created_at": iso(v.created_at)} for v in versions],
            "validation": validate_definition(w.draft_definition, org_features(db, ctx.org_id))}


@router.put("/{wf_id}")
def update_workflow(wf_id: uuid.UUID, body: WorkflowUpdate, ctx: OrgContext = Depends(require("workflows.write")), db: Session = Depends(get_db)):
    w = get_wf(db, ctx, wf_id)
    if body.name:
        w.name = body.name
    if body.description is not None:
        w.description = body.description
    if body.definition is not None:
        if not isinstance(body.definition.get("nodes"), list) or not isinstance(body.definition.get("edges", []), list):
            raise bad_request("definition must have nodes and edges arrays")
        w.draft_definition = body.definition
    return {**wf_out(w, ctx, True), "validation": validate_definition(w.draft_definition, org_features(db, ctx.org_id))}


@router.post("/{wf_id}/validate")
def validate(wf_id: uuid.UUID, ctx: OrgContext = Depends(require("workflows.read")), db: Session = Depends(get_db)):
    return validate_definition(get_wf(db, ctx, wf_id).draft_definition, org_features(db, ctx.org_id))


@router.post("/{wf_id}/publish")
def publish_ep(wf_id: uuid.UUID, ctx: OrgContext = Depends(require("workflows.write")), db: Session = Depends(get_db)):
    w = get_wf(db, ctx, wf_id)
    v = publish(db, w, ctx.user.id)
    audit_ctx(db, ctx, "workflow.published", "workflow", w.id, {"version": v.version})
    return wf_out(w, ctx, True)


@router.post("/{wf_id}/pause")
def pause(wf_id: uuid.UUID, ctx: OrgContext = Depends(require("workflows.write")), db: Session = Depends(get_db)):
    w = get_wf(db, ctx, wf_id)
    if w.status == "published":
        w.status = "paused"
    elif w.status == "paused":
        w.status = "published"
    audit_ctx(db, ctx, f"workflow.{w.status}", "workflow", w.id)
    return wf_out(w, ctx, True)


@router.post("/{wf_id}/versions/{version}/restore")
def restore(wf_id: uuid.UUID, version: int, ctx: OrgContext = Depends(require("workflows.write")), db: Session = Depends(get_db)):
    w = get_wf(db, ctx, wf_id)
    v = db.scalar(select(WorkflowVersion).where(WorkflowVersion.workflow_id == w.id, WorkflowVersion.version == version))
    if not v:
        raise not_found("Version")
    w.draft_definition = v.definition
    return wf_out(w, ctx, True)


@router.delete("/{wf_id}")
def archive(wf_id: uuid.UUID, ctx: OrgContext = Depends(require("workflows.write")), db: Session = Depends(get_db)):
    w = get_wf(db, ctx, wf_id)
    w.status = "archived"
    audit_ctx(db, ctx, "workflow.archived", "workflow", w.id)
    return {"ok": True}


class RunIn(BaseModel):
    input: dict = {}
    sync: bool = False


def ex_out(e: WorkflowExecution, logs=None) -> dict:
    d = {"id": str(e.id), "workflow_id": str(e.workflow_id), "version": e.version, "trigger": e.trigger, "status": e.status,
         "input": e.input, "output": e.output, "error": e.error, "attempt": e.attempt, "retry_of": str(e.retry_of) if e.retry_of else None,
         "created_at": iso(e.created_at), "started_at": iso(e.started_at), "finished_at": iso(e.finished_at), "duration_ms": e.duration_ms}
    if logs is not None:
        d["logs"] = [{"node_id": l.node_id, "node_type": l.node_type, "status": l.status, "input": l.input, "output": l.output,
                      "error": l.error, "started_at": iso(l.started_at), "duration_ms": l.duration_ms} for l in logs]
    return d


@router.post("/{wf_id}/run", status_code=201)
def run(wf_id: uuid.UUID, body: RunIn, ctx: OrgContext = Depends(require("workflows.run")), db: Session = Depends(get_db)):
    w = get_wf(db, ctx, wf_id)
    ex = create_execution(db, w, "manual", body.input, user_id=ctx.user.id)
    if body.sync:
        from app.workflows.service import execute
        execute(db, ex)
    return ex_out(ex)


@router.get("/{wf_id}/executions")
def executions(wf_id: uuid.UUID, status: str | None = None, ctx: OrgContext = Depends(require("workflows.read")), db: Session = Depends(get_db)):
    w = get_wf(db, ctx, wf_id)
    q = select(WorkflowExecution).where(WorkflowExecution.workflow_id == w.id, WorkflowExecution.org_id == ctx.org_id)
    if status:
        q = q.where(WorkflowExecution.status == status)
    return [ex_out(e) for e in db.scalars(q.order_by(WorkflowExecution.created_at.desc()).limit(100))]


@router.get("/executions/{ex_id}")
def execution(ex_id: uuid.UUID, ctx: OrgContext = Depends(require("workflows.read")), db: Session = Depends(get_db)):
    e = db.get(WorkflowExecution, ex_id)
    if not e or e.org_id != ctx.org_id:
        raise not_found("Execution")
    logs = db.scalars(select(WorkflowExecutionLog).where(WorkflowExecutionLog.execution_id == e.id, WorkflowExecutionLog.org_id == ctx.org_id)
                      .order_by(WorkflowExecutionLog.started_at)).all()
    return ex_out(e, logs)


@router.post("/executions/{ex_id}/retry", status_code=201)
def retry(ex_id: uuid.UUID, ctx: OrgContext = Depends(require("workflows.run")), db: Session = Depends(get_db)):
    e = db.get(WorkflowExecution, ex_id)
    if not e or e.org_id != ctx.org_id:
        raise not_found("Execution")
    if e.status != "failed":
        raise bad_request("Only failed executions can be retried")
    w = db.get(Workflow, e.workflow_id)
    new = create_execution(db, w, e.trigger, e.input, user_id=ctx.user.id, retry_of=e.id, attempt=e.attempt + 1)
    audit_ctx(db, ctx, "workflow.execution_retried", "workflow_execution", e.id)
    return ex_out(new)


@router.post("/executions/{ex_id}/cancel")
def cancel(ex_id: uuid.UUID, ctx: OrgContext = Depends(require("workflows.run")), db: Session = Depends(get_db)):
    e = db.get(WorkflowExecution, ex_id)
    if not e or e.org_id != ctx.org_id:
        raise not_found("Execution")
    if e.status in ("succeeded", "failed", "cancelled"):
        raise bad_request("Execution already finished")
    e.status, e.finished_at = "cancelled", datetime.now(timezone.utc)
    return ex_out(e)


@router.get("/{wf_id}/analytics")
def analytics(wf_id: uuid.UUID, days: int = 30, ctx: OrgContext = Depends(require("workflows.read")), db: Session = Depends(get_db)):
    w = get_wf(db, ctx, wf_id)
    since = datetime.now(timezone.utc) - timedelta(days=min(days, 365))
    rows = db.scalars(select(WorkflowExecution).where(WorkflowExecution.workflow_id == w.id, WorkflowExecution.created_at >= since)).all()
    by_day: dict[str, dict] = {}
    for e in rows:
        k = e.created_at.date().isoformat()
        b = by_day.setdefault(k, {"date": k, "succeeded": 0, "failed": 0, "other": 0})
        b[e.status if e.status in ("succeeded", "failed") else "other"] += 1
    node_fail = db.execute(select(WorkflowExecutionLog.node_id, WorkflowExecutionLog.node_type, func.count())
                           .join(WorkflowExecution, WorkflowExecution.id == WorkflowExecutionLog.execution_id)
                           .where(WorkflowExecution.workflow_id == w.id, WorkflowExecutionLog.status == "failed", WorkflowExecution.created_at >= since)
                           .group_by(WorkflowExecutionLog.node_id, WorkflowExecutionLog.node_type)).all()
    durations = [e.duration_ms for e in rows if e.duration_ms is not None]
    n = len(rows)
    ok = sum(e.status == "succeeded" for e in rows)
    fin = sum(e.status in ("succeeded", "failed") for e in rows)
    return {"total": n, "succeeded": ok, "failed": sum(e.status == "failed" for e in rows), "success_rate": round(ok / fin, 3) if fin else None,
            "avg_duration_ms": int(sum(durations) / len(durations)) if durations else None, "daily": sorted(by_day.values(), key=lambda x: x["date"]),
            "failing_nodes": [{"node_id": a, "node_type": b, "failures": c} for a, b, c in node_fail]}
