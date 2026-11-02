"""Module 8: executive BI dashboard. Every metric is computed from recorded rows; estimates are labelled with their method."""
import csv
import io
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import OrgContext, require
from app.core.errors import bad_request
from app.models import AnalyticsEvent, AIRequest, Membership, AgentRun, WorkflowExecution, Task, Document, User

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Minutes of manual work replaced per outcome. Assumptions, not measurements — see ANALYTICS_FRAMEWORK.md §Time saved.
TIME_SAVED_MINUTES = {"knowledge_answer": 6, "document_summarised": 10, "data_extracted": 8, "report_generated": 45, "agent_run_completed": 15,
                      "workflow_completed": 5, "tasks_created_from_notes": 3, "data_question_answered": 12, "task_completed": 0}
FEATURE_EVENTS = {"assistant": "ai_query_completed", "knowledge": "document_uploaded", "agents": "agent_executed", "workflows": "workflow_executed",
                  "data": "dataset_queried", "tasks": "task_created"}


def _range(days: int):
    if days not in (7, 14, 30, 90, 180, 365):
        raise bad_request("days must be one of 7, 14, 30, 90, 180, 365")
    end = datetime.now(timezone.utc)
    return end - timedelta(days=days), end


def _counts(db, org_id, start, end) -> dict:
    ev = dict(db.execute(select(AnalyticsEvent.event, func.count()).where(AnalyticsEvent.org_id == org_id, AnalyticsEvent.created_at >= start,
                                                                         AnalyticsEvent.created_at < end).group_by(AnalyticsEvent.event)).all())
    ai = db.execute(select(func.count(), func.coalesce(func.sum(AIRequest.input_tokens + AIRequest.output_tokens), 0),
                           func.coalesce(func.sum(AIRequest.cost_usd), 0), func.count().filter(AIRequest.status == "error"),
                           func.coalesce(func.avg(AIRequest.latency_ms).filter(AIRequest.status == "success"), 0),
                           func.count().filter(AIRequest.cache_hit.is_(True)))
                    .where(AIRequest.org_id == org_id, AIRequest.created_at >= start, AIRequest.created_at < end)).one()
    active = db.scalar(select(func.count(func.distinct(AnalyticsEvent.user_id))).where(AnalyticsEvent.org_id == org_id, AnalyticsEvent.created_at >= start,
                                                                                    AnalyticsEvent.created_at < end, AnalyticsEvent.user_id.is_not(None)))
    wf = dict(db.execute(select(WorkflowExecution.status, func.count()).where(WorkflowExecution.org_id == org_id, WorkflowExecution.created_at >= start,
                                                                            WorkflowExecution.created_at < end).group_by(WorkflowExecution.status)).all())
    runs = db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.org_id == org_id, AgentRun.created_at >= start, AgentRun.created_at < end))
    created = db.scalar(select(func.count()).select_from(Task).where(Task.org_id == org_id, Task.created_at >= start, Task.created_at < end))
    done = db.scalar(select(func.count()).select_from(Task).where(Task.org_id == org_id, Task.completed_at >= start, Task.completed_at < end))
    outcomes = dict(db.execute(text("""SELECT properties->>'outcome_type', count(*) FROM analytics_events WHERE org_id = :o AND event = 'outcome_achieved'
                                     AND created_at >= :s AND created_at < :e GROUP BY 1"""), {"o": org_id, "s": start, "e": end}).all())
    minutes = sum(TIME_SAVED_MINUTES.get(k, 0) * v for k, v in outcomes.items())
    return {"active_users": active, "ai_interactions": ev.get("ai_query_completed", 0), "ai_requests": ai[0], "tokens": int(ai[1]),
            "ai_cost_usd": round(float(ai[2]), 4), "ai_errors": ai[3], "avg_ai_latency_ms": int(ai[4] or 0), "ai_cache_hits": ai[5],
            "documents_processed": ev.get("document_indexed", 0), "agents_executed": runs, "workflows_executed": sum(wf.values()),
            "workflows_succeeded": wf.get("succeeded", 0), "workflows_failed": wf.get("failed", 0), "tasks_created": created, "tasks_completed": done,
            "outcomes": sum(outcomes.values()), "outcomes_by_type": outcomes, "time_saved_hours_estimate": round(minutes / 60, 1)}


def _delta(cur, prev):
    if not isinstance(cur, (int, float)) or not isinstance(prev, (int, float)):
        return None
    if prev == 0:
        return None if cur == 0 else 1.0
    return round((cur - prev) / prev, 3)


@router.get("/dashboard")
def dashboard(days: int = 30, ctx: OrgContext = Depends(require("analytics.read")), db: Session = Depends(get_db)):
    start, end = _range(days)
    cur = _counts(db, ctx.org_id, start, end)
    prev = _counts(db, ctx.org_id, start - (end - start), start)
    total_users = db.scalar(select(func.count()).select_from(Membership).where(Membership.org_id == ctx.org_id, Membership.status == "active"))
    open_tasks = db.scalar(select(func.count()).select_from(Task).where(Task.org_id == ctx.org_id, Task.status != "done"))
    all_tasks = db.scalar(select(func.count()).select_from(Task).where(Task.org_id == ctx.org_id))
    docs = db.scalar(select(func.count()).select_from(Document).where(Document.org_id == ctx.org_id, Document.deleted_at.is_(None)))
    # feature adoption = share of active users who used the feature in the period
    adoption = {}
    for feat, ev in FEATURE_EVENTS.items():
        n = db.scalar(select(func.count(func.distinct(AnalyticsEvent.user_id))).where(AnalyticsEvent.org_id == ctx.org_id, AnalyticsEvent.event == ev,
                                                                                    AnalyticsEvent.created_at >= start))
        adoption[feat] = {"users": n, "rate": round(n / cur["active_users"], 3) if cur["active_users"] else 0}
    wf_total = cur["workflows_succeeded"] + cur["workflows_failed"]
    return {"range": {"days": days, "start": start.isoformat(), "end": end.isoformat()},
            "kpis": {k: {"value": v, "previous": prev.get(k), "delta": _delta(v, prev.get(k))} for k, v in cur.items() if k != "outcomes_by_type"},
            "totals": {"total_users": total_users, "documents": docs, "open_tasks": open_tasks,
                       "task_completion_rate": round((all_tasks - open_tasks) / all_tasks, 3) if all_tasks else None,
                       "workflow_success_rate": round(cur["workflows_succeeded"] / wf_total, 3) if wf_total else None},
            "outcomes_by_type": cur["outcomes_by_type"], "feature_adoption": adoption,
            "estimates": {"time_saved_hours": {"value": cur["time_saved_hours_estimate"], "is_estimate": True,
                                               "method": "Σ(outcomes × assumed manual minutes per outcome type)", "assumptions_minutes": TIME_SAVED_MINUTES}},
            "measured_vs_estimated": {"measured": [k for k in cur if k != "time_saved_hours_estimate"], "estimated": ["time_saved_hours_estimate"]}}


@router.get("/timeseries")
def timeseries(days: int = 30, granularity: str = "day", ctx: OrgContext = Depends(require("analytics.read")), db: Session = Depends(get_db)):
    if granularity not in ("day", "week", "month"):
        raise bad_request("granularity must be day, week or month")
    start, end = _range(days)
    p = {"o": ctx.org_id, "s": start, "g": granularity}
    ev = db.execute(text("""SELECT date_trunc(:g, created_at) AS b, event, count(*) FROM analytics_events WHERE org_id = :o AND created_at >= :s
                           AND event IN ('ai_query_completed','document_indexed','agent_executed','workflow_completed','workflow_failed','outcome_achieved','task_completed')
                           GROUP BY 1, 2"""), p).all()
    ai = db.execute(text("""SELECT date_trunc(:g, created_at) AS b, sum(input_tokens + output_tokens), sum(cost_usd), count(*) FROM ai_requests
                           WHERE org_id = :o AND created_at >= :s GROUP BY 1"""), p).all()
    buckets: dict = {}
    cur = start.replace(hour=0, minute=0, second=0, microsecond=0)
    step = {"day": timedelta(days=1), "week": timedelta(days=7), "month": timedelta(days=31)}[granularity]
    while cur <= end:
        k = db.scalar(text("SELECT date_trunc(:g, CAST(:t AS timestamptz))"), {"g": granularity, "t": cur})
        buckets.setdefault(k.isoformat(), {"bucket": k.isoformat()})
        cur += step
    for b, e, c in ev:
        buckets.setdefault(b.isoformat(), {"bucket": b.isoformat()})[e] = c
    for b, tok, cost, n in ai:
        d = buckets.setdefault(b.isoformat(), {"bucket": b.isoformat()})
        d.update({"tokens": int(tok or 0), "ai_cost_usd": round(float(cost or 0), 4), "ai_requests": n})
    keys = ["ai_query_completed", "document_indexed", "agent_executed", "workflow_completed", "workflow_failed", "outcome_achieved", "task_completed",
            "tokens", "ai_cost_usd", "ai_requests"]
    rows = [{k2: v.get(k2, 0) for k2 in keys} | {"bucket": v["bucket"]} for _, v in sorted(buckets.items())]
    return {"granularity": granularity, "series": rows}


@router.get("/drilldown")
def drilldown(metric: str, group: str, days: int = 30, ctx: OrgContext = Depends(require("analytics.read")), db: Session = Depends(get_db)):
    start, _ = _range(days)
    if metric in ("ai_cost", "tokens", "ai_requests", "latency"):
        col = {"model": AIRequest.model, "feature": AIRequest.feature, "provider": AIRequest.provider, "task_type": AIRequest.task_type,
               "user": AIRequest.user_id}.get(group)
        if col is None:
            raise bad_request("group must be model, feature, provider, task_type or user")
        val = {"ai_cost": func.sum(AIRequest.cost_usd), "tokens": func.sum(AIRequest.input_tokens + AIRequest.output_tokens),
               "ai_requests": func.count(), "latency": func.avg(AIRequest.latency_ms)}[metric]
        rows = db.execute(select(col, val).where(AIRequest.org_id == ctx.org_id, AIRequest.created_at >= start).group_by(col).order_by(val.desc())).all()
    elif metric == "events":
        col = {"event": AnalyticsEvent.event, "user": AnalyticsEvent.user_id}.get(group)
        if col is None:
            raise bad_request("group must be event or user")
        rows = db.execute(select(col, func.count()).where(AnalyticsEvent.org_id == ctx.org_id, AnalyticsEvent.created_at >= start)
                          .group_by(col).order_by(func.count().desc()).limit(50)).all()
    else:
        raise bad_request("Unknown metric")
    out = [{"key": str(k) if k is not None else "unknown", "value": float(v or 0)} for k, v in rows]
    if group == "user":
        users = {str(u.id): u.full_name or u.email for u in db.scalars(select(User).where(User.id.in_([r[0] for r in rows if r[0]])))}
        for o in out:
            o["label"] = users.get(o["key"], o["key"])
    return {"metric": metric, "group": group, "rows": out}


@router.get("/export")
def export(days: int = 30, ctx: OrgContext = Depends(require("analytics.read")), db: Session = Depends(get_db)):
    data = timeseries(days, "day", ctx, db)["series"]
    buf = io.StringIO()
    if data:
        w = csv.DictWriter(buf, fieldnames=list(data[0].keys()))
        w.writeheader()
        w.writerows(data)
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="nexora-analytics-{days}d.csv"'})


@router.get("/ai-usage")
def ai_usage(days: int = 30, ctx: OrgContext = Depends(require("analytics.read")), db: Session = Depends(get_db)):
    start, _ = _range(days)
    rows = db.execute(select(AIRequest.provider, AIRequest.model, func.count(), func.sum(AIRequest.input_tokens), func.sum(AIRequest.output_tokens),
                             func.sum(AIRequest.cached_tokens), func.sum(AIRequest.cost_usd), func.avg(AIRequest.latency_ms),
                             func.count().filter(AIRequest.status == "error"), func.count().filter(AIRequest.fallback_used.is_(True)))
                      .where(AIRequest.org_id == ctx.org_id, AIRequest.created_at >= start).group_by(AIRequest.provider, AIRequest.model)).all()
    outcomes = db.scalar(select(func.count()).select_from(AnalyticsEvent).where(AnalyticsEvent.org_id == ctx.org_id, AnalyticsEvent.event == "outcome_achieved",
                                                                              AnalyticsEvent.created_at >= start))
    total_cost = sum(float(r[6] or 0) for r in rows)
    return {"by_model": [{"provider": r[0], "model": r[1], "requests": r[2], "input_tokens": int(r[3] or 0), "output_tokens": int(r[4] or 0),
                          "cached_tokens": int(r[5] or 0), "cost_usd": round(float(r[6] or 0), 4), "avg_latency_ms": int(r[7] or 0),
                          "errors": r[8], "fallbacks": r[9]} for r in rows],
            "total_cost_usd": round(total_cost, 4), "outcomes": outcomes,
            "cost_per_outcome_usd": round(total_cost / outcomes, 4) if outcomes else None}
