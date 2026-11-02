"""Module 4: AI Agent Studio + human approvals."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.agents.runtime import start_run, advance, decide_approval
from app.agents.templates import TEMPLATES
from app.agents.tools import REGISTRY, tool_catalog
from app.core.audit import audit_ctx, track
from app.core.db import get_db
from app.core.deps import OrgContext, require
from app.core.errors import not_found, bad_request, forbidden
from app.core.permissions import role_at_least
from app.core.plans import check_limit, require_feature, has_feature
from app.models import Agent, AgentRun, AgentRunStep, Approval, User
from app.modules.common import iso, user_brief
from app.worker.queue import enqueue

router = APIRouter(prefix="/api/agents", tags=["agents"])
approvals_router = APIRouter(prefix="/api/approvals", tags=["approvals"])
ROUTERS = [router, approvals_router]
ADVANCED_TOOLS = {"fetch_url", "send_webhook", "query_dataset"}


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    instructions: str = Field(min_length=10, max_length=20000)
    template_key: str | None = None
    model_route: str = "agent"
    tools: list[str] = []
    approval_required_tools: list[str] = []
    knowledge_document_ids: list[str] | None = None
    use_knowledge: bool = True
    memory_enabled: bool = False
    max_steps: int = Field(default=6, ge=1, le=20)
    max_tokens_per_run: int = Field(default=20000, ge=1000, le=200000)
    output_format: str = "markdown"
    output_schema: dict | None = None
    status: str = "active"


def agent_out(a: Agent) -> dict:
    return {"id": str(a.id), "name": a.name, "description": a.description, "instructions": a.instructions, "template_key": a.template_key,
            "model_route": a.model_route, "tools": a.tools, "approval_required_tools": a.approval_required_tools,
            "knowledge_document_ids": a.knowledge_document_ids, "use_knowledge": a.use_knowledge, "memory_enabled": a.memory_enabled,
            "memory": a.memory, "max_steps": a.max_steps, "max_tokens_per_run": a.max_tokens_per_run, "output_format": a.output_format,
            "output_schema": a.output_schema, "status": a.status, "created_at": iso(a.created_at), "updated_at": iso(a.updated_at)}


def _validate(db: Session, ctx: OrgContext, body: AgentIn):
    unknown = [t for t in body.tools if t not in REGISTRY]
    if unknown:
        raise bad_request(f"Unknown tools: {', '.join(unknown)}")
    if set(body.approval_required_tools) - set(body.tools):
        raise bad_request("Approval-required tools must be a subset of the agent's tools")
    if body.output_format not in ("markdown", "json", "text"):
        raise bad_request("Invalid output format")
    if body.model_route not in ("agent", "chat", "analysis", "fast", "balanced", "frontier", "auto"):
        raise bad_request("Invalid model route")
    if body.output_schema is not None and body.output_schema.get("type") != "object":
        raise bad_request("output_schema must be a JSON object schema")
    for t in body.tools:
        if not role_at_least(ctx.role, REGISTRY[t].min_role):
            raise forbidden(f"You cannot grant '{t}' (requires {REGISTRY[t].min_role})")
    if set(body.tools) & ADVANCED_TOOLS and not has_feature(db, ctx.org_id, "agents_advanced"):
        require_feature(db, ctx.org_id, "agents_advanced")


def get_agent(db, ctx, agent_id) -> Agent:
    a = db.get(Agent, agent_id)
    if not a or a.org_id != ctx.org_id:
        raise not_found("Agent")
    return a


@router.get("/templates")
def templates(ctx: OrgContext = Depends(require("agents.read"))):
    return [{"key": k, **v} for k, v in TEMPLATES.items()]


@router.get("/tools")
def tools(ctx: OrgContext = Depends(require("agents.read"))):
    return tool_catalog()


@router.get("")
def list_agents(ctx: OrgContext = Depends(require("agents.read")), db: Session = Depends(get_db)):
    agents = db.scalars(select(Agent).where(Agent.org_id == ctx.org_id, Agent.status != "archived").order_by(Agent.created_at.desc())).all()
    stats = {r[0]: r for r in db.execute(select(AgentRun.agent_id, func.count(), func.count().filter(AgentRun.status == "succeeded"),
                                                func.max(AgentRun.created_at)).where(AgentRun.org_id == ctx.org_id).group_by(AgentRun.agent_id))}
    out = []
    for a in agents:
        s = stats.get(a.id)
        out.append({**agent_out(a), "runs": s[1] if s else 0, "success_rate": round(s[2] / s[1], 3) if s and s[1] else None,
                    "last_run_at": iso(s[3]) if s else None})
    return out


@router.post("", status_code=201)
def create_agent(body: AgentIn, ctx: OrgContext = Depends(require("agents.write")), db: Session = Depends(get_db)):
    check_limit(db, ctx.org_id, "agents")
    _validate(db, ctx, body)
    a = Agent(org_id=ctx.org_id, created_by=ctx.user.id, **body.model_dump())
    db.add(a)
    db.flush()
    audit_ctx(db, ctx, "agent.created", "agent", a.id, {"tools": body.tools})
    track(db, "agent_created", org_id=ctx.org_id, user_id=ctx.user.id, properties={"template": body.template_key, "tools": len(body.tools)})
    return agent_out(a)


@router.post("/from-template/{key}", status_code=201)
def from_template(key: str, ctx: OrgContext = Depends(require("agents.write")), db: Session = Depends(get_db)):
    t = TEMPLATES.get(key)
    if not t:
        raise not_found("Template")
    body = AgentIn(name=t["name"], description=t["description"], instructions=t["instructions"], template_key=key, tools=t["tools"],
                   approval_required_tools=t.get("approval_required_tools", []), output_format=t.get("output_format", "markdown"),
                   output_schema=t.get("output_schema"), model_route=t.get("model_route", "agent"))
    if not has_feature(db, ctx.org_id, "agents_advanced"):
        body.tools = [x for x in body.tools if x not in ADVANCED_TOOLS]
        body.approval_required_tools = [x for x in body.approval_required_tools if x in body.tools]
    return create_agent(body, ctx, db)


@router.get("/{agent_id}")
def get_agent_ep(agent_id: uuid.UUID, ctx: OrgContext = Depends(require("agents.read")), db: Session = Depends(get_db)):
    return agent_out(get_agent(db, ctx, agent_id))


@router.put("/{agent_id}")
def update_agent(agent_id: uuid.UUID, body: AgentIn, ctx: OrgContext = Depends(require("agents.write")), db: Session = Depends(get_db)):
    a = get_agent(db, ctx, agent_id)
    _validate(db, ctx, body)
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    audit_ctx(db, ctx, "agent.updated", "agent", a.id, {"tools": body.tools})
    return agent_out(a)


@router.delete("/{agent_id}")
def archive_agent(agent_id: uuid.UUID, ctx: OrgContext = Depends(require("agents.write")), db: Session = Depends(get_db)):
    a = get_agent(db, ctx, agent_id)
    a.status = "archived"
    audit_ctx(db, ctx, "agent.archived", "agent", a.id)
    return {"ok": True}


@router.post("/{agent_id}/memory/clear")
def clear_memory(agent_id: uuid.UUID, ctx: OrgContext = Depends(require("agents.write")), db: Session = Depends(get_db)):
    a = get_agent(db, ctx, agent_id)
    a.memory = []
    return {"ok": True}


class RunIn(BaseModel):
    input: str = Field(min_length=1, max_length=20000)
    sync: bool = False


def run_out(r: AgentRun, steps=None) -> dict:
    d = {"id": str(r.id), "agent_id": str(r.agent_id), "input": r.input, "status": r.status, "output": r.output,
         "structured_output": r.structured_output, "error": r.error, "steps_count": r.steps_count, "total_tokens": r.total_tokens,
         "cost_usd": float(r.cost_usd or 0), "created_at": iso(r.created_at), "started_at": iso(r.started_at), "finished_at": iso(r.finished_at),
         "duration_ms": int((r.finished_at - r.started_at).total_seconds() * 1000) if r.finished_at and r.started_at else None,
         "pending_approvals": [p.get("approval_id") for p in (r.state or {}).get("pending", []) if not p.get("decision")]}
    if steps is not None:
        d["steps"] = [{"idx": s.idx, "type": s.type, "tool": s.tool, "input": s.input, "output": s.output, "status": s.status,
                       "latency_ms": s.latency_ms, "attempt": s.attempt, "created_at": iso(s.created_at)} for s in steps]
    return d


@router.post("/{agent_id}/runs", status_code=201)
def run_agent(agent_id: uuid.UUID, body: RunIn, ctx: OrgContext = Depends(require("agents.run")), db: Session = Depends(get_db)):
    a = get_agent(db, ctx, agent_id)
    if a.status != "active":
        raise bad_request("Agent is not active")
    check_limit(db, ctx.org_id, "agent_runs")
    run = start_run(db, a, ctx.user.id, ctx.role, body.input)
    if body.sync:
        advance(db, run)
    else:
        enqueue(db, "run_agent", {"run_id": str(run.id)}, org_id=ctx.org_id, max_attempts=1)
    db.flush()
    steps = db.scalars(select(AgentRunStep).where(AgentRunStep.run_id == run.id).order_by(AgentRunStep.idx)).all()
    return run_out(run, steps)


@router.get("/{agent_id}/runs")
def list_runs(agent_id: uuid.UUID, ctx: OrgContext = Depends(require("agents.read")), db: Session = Depends(get_db)):
    a = get_agent(db, ctx, agent_id)
    return [run_out(r) for r in db.scalars(select(AgentRun).where(AgentRun.agent_id == a.id, AgentRun.org_id == ctx.org_id)
                                           .order_by(AgentRun.created_at.desc()).limit(50))]


@router.get("/runs/{run_id}")
def get_run(run_id: uuid.UUID, ctx: OrgContext = Depends(require("agents.read")), db: Session = Depends(get_db)):
    r = db.get(AgentRun, run_id)
    if not r or r.org_id != ctx.org_id:
        raise not_found("Run")
    steps = db.scalars(select(AgentRunStep).where(AgentRunStep.run_id == r.id, AgentRunStep.org_id == ctx.org_id).order_by(AgentRunStep.idx)).all()
    return run_out(r, steps)


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: uuid.UUID, ctx: OrgContext = Depends(require("agents.run")), db: Session = Depends(get_db)):
    r = db.get(AgentRun, run_id)
    if not r or r.org_id != ctx.org_id:
        raise not_found("Run")
    if r.status in ("succeeded", "failed", "cancelled"):
        raise bad_request("Run already finished")
    r.status, r.finished_at = "cancelled", datetime.now(timezone.utc)
    for ap in db.scalars(select(Approval).where(Approval.source_id == r.id, Approval.status == "pending")):
        ap.status = "cancelled"
    return run_out(r)


@router.get("/{agent_id}/metrics")
def agent_metrics(agent_id: uuid.UUID, ctx: OrgContext = Depends(require("agents.read")), db: Session = Depends(get_db)):
    a = get_agent(db, ctx, agent_id)
    runs = db.scalars(select(AgentRun).where(AgentRun.agent_id == a.id, AgentRun.org_id == ctx.org_id).order_by(AgentRun.created_at.desc()).limit(500)).all()
    done = [r for r in runs if r.finished_at and r.started_at]
    tool_counts = dict(db.execute(select(AgentRunStep.tool, func.count()).join(AgentRun, AgentRun.id == AgentRunStep.run_id)
                                  .where(AgentRun.agent_id == a.id, AgentRunStep.type == "tool_call", AgentRunStep.org_id == ctx.org_id)
                                  .group_by(AgentRunStep.tool)).all())
    tool_errors = dict(db.execute(select(AgentRunStep.tool, func.count()).join(AgentRun, AgentRun.id == AgentRunStep.run_id)
                                  .where(AgentRun.agent_id == a.id, AgentRunStep.type == "tool_call", AgentRunStep.status != "ok",
                                         AgentRunStep.org_id == ctx.org_id).group_by(AgentRunStep.tool)).all())
    n = len(runs)
    return {"runs": n, "succeeded": sum(r.status == "succeeded" for r in runs), "failed": sum(r.status == "failed" for r in runs),
            "awaiting_approval": sum(r.status == "awaiting_approval" for r in runs),
            "success_rate": round(sum(r.status == "succeeded" for r in runs) / n, 3) if n else None,
            "avg_duration_ms": int(sum((r.finished_at - r.started_at).total_seconds() * 1000 for r in done) / len(done)) if done else None,
            "avg_tokens": int(sum(r.total_tokens for r in runs) / n) if n else 0,
            "total_cost_usd": round(sum(float(r.cost_usd or 0) for r in runs), 4),
            "tool_usage": [{"tool": k, "calls": v, "errors": tool_errors.get(k, 0)} for k, v in tool_counts.items()]}


# ---------------- approvals (shared by agents and workflows) ----------------
def approval_out(a: Approval, requester: User | None = None) -> dict:
    return {"id": str(a.id), "source_type": a.source_type, "source_id": str(a.source_id), "title": a.title, "details": a.details,
            "status": a.status, "required_role": a.required_role, "requested_by": user_brief(requester), "decision_note": a.decision_note,
            "decided_at": iso(a.decided_at), "created_at": iso(a.created_at)}


@approvals_router.get("")
def list_approvals(status: str = "pending", ctx: OrgContext = Depends(require("agents.read")), db: Session = Depends(get_db)):
    q = select(Approval).where(Approval.org_id == ctx.org_id)
    if status != "all":
        q = q.where(Approval.status == status)
    rows = db.scalars(q.order_by(Approval.created_at.desc()).limit(200)).all()
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({r.requested_by for r in rows if r.requested_by})))} if rows else {}
    return [approval_out(a, users.get(a.requested_by)) for a in rows]


class DecisionIn(BaseModel):
    decision: str
    note: str | None = Field(default=None, max_length=2000)


@approvals_router.post("/{approval_id}/decide")
def decide(approval_id: uuid.UUID, body: DecisionIn, ctx: OrgContext = Depends(require("approvals.decide")), db: Session = Depends(get_db)):
    ap = db.get(Approval, approval_id)
    if not ap or ap.org_id != ctx.org_id:
        raise not_found("Approval")
    if ap.status != "pending":
        raise bad_request("This approval has already been decided")
    if body.decision not in ("approved", "rejected"):
        raise bad_request("decision must be approved or rejected")
    if not role_at_least(ctx.role, ap.required_role):
        raise forbidden(f"Requires {ap.required_role} role")
    ap.status, ap.decided_by, ap.decided_at, ap.decision_note = body.decision, ctx.user.id, datetime.now(timezone.utc), body.note
    if ap.source_type == "agent_run":
        decide_approval(db, ap, body.decision, body.note, ctx.user.id)
    elif ap.source_type == "workflow_execution":
        from app.workflows.service import resume_after_approval
        resume_after_approval(db, ap, body.decision)
    audit_ctx(db, ctx, f"approval.{body.decision}", "approval", ap.id, {"title": ap.title, "details": ap.details})
    track(db, "approval_decided", org_id=ctx.org_id, user_id=ctx.user.id, properties={"decision": body.decision, "source": ap.source_type})
    return approval_out(ap)
