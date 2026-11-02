"""Plan catalogue, usage metering and plan enforcement. Pricing rationale: docs/MONETISATION_STRATEGY.md."""
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from app.core.errors import plan_limit
from app.models import Subscription, UsageCounter, Membership, Document, Agent, Workflow, Dataset, Workspace

UNLIMITED = -1

PLANS: dict[str, dict] = {
    "free": {
        "name": "Free", "price_usd": 0, "price_inr": 0, "seats_included": 2,
        "limits": {"ai_messages": 150, "documents": 10, "storage_mb": 100, "agents": 1, "workflows": 1,
                   "workflow_runs": 50, "agent_runs": 25, "datasets": 1, "members": 2, "workspaces": 1, "integrations": 1},
        "features": ["assistant", "knowledge", "tasks", "analytics_basic"],
    },
    "starter": {
        "name": "Starter", "price_usd": 49, "price_inr": 3999, "seats_included": 5,
        "limits": {"ai_messages": 2000, "documents": 200, "storage_mb": 5000, "agents": 5, "workflows": 10,
                   "workflow_runs": 2000, "agent_runs": 500, "datasets": 5, "members": 5, "workspaces": 3, "integrations": 5},
        "features": ["assistant", "knowledge", "tasks", "analytics_basic", "agents", "workflows", "team"],
    },
    "professional": {
        "name": "Professional", "price_usd": 199, "price_inr": 15999, "seats_included": 20,
        "limits": {"ai_messages": 10000, "documents": 2000, "storage_mb": 50000, "agents": 25, "workflows": 100,
                   "workflow_runs": 20000, "agent_runs": 5000, "datasets": 50, "members": 20, "workspaces": 10, "integrations": UNLIMITED},
        "features": ["assistant", "knowledge", "tasks", "analytics_basic", "agents", "workflows", "team",
                     "agents_advanced", "workflows_advanced", "data_intelligence", "integrations_advanced", "team_admin", "audit_logs"],
    },
    "enterprise": {
        "name": "Enterprise", "price_usd": None, "price_inr": None, "seats_included": None,
        "limits": {k: UNLIMITED for k in ["ai_messages", "documents", "storage_mb", "agents", "workflows", "workflow_runs",
                                          "agent_runs", "datasets", "members", "workspaces", "integrations"]},
        "features": ["assistant", "knowledge", "tasks", "analytics_basic", "agents", "workflows", "team", "agents_advanced",
                     "workflows_advanced", "data_intelligence", "integrations_advanced", "team_admin", "audit_logs",
                     "custom_limits", "sso", "audit_export", "priority_support"],
    },
}
PLAN_ORDER = ["free", "starter", "professional", "enterprise"]
TRIAL_PLAN = "professional"
TRIAL_DAYS = 14

# Metrics counted per calendar month vs. counted as current totals.
MONTHLY_METRICS = {"ai_messages", "workflow_runs", "agent_runs"}


def period_key(dt: datetime | None = None) -> str:
    return (dt or datetime.now(timezone.utc)).strftime("%Y-%m")


def get_subscription(db: Session, org_id) -> Subscription:
    sub = db.scalar(select(Subscription).where(Subscription.org_id == org_id))
    if sub is None:
        sub = Subscription(org_id=org_id, plan="free", status="active", provider="none")
        db.add(sub)
        db.flush()
    # Trial expiry is evaluated lazily so no cron is required for correctness.
    if sub.status == "trialing" and sub.trial_ends_at and sub.trial_ends_at < datetime.now(timezone.utc):
        sub.plan, sub.status, sub.trial_ends_at = "free", "active", None
    return sub


def effective_plan(db: Session, org_id) -> dict:
    sub = get_subscription(db, org_id)
    plan = dict(PLANS[sub.plan])
    limits = dict(plan["limits"])
    limits.update(sub.custom_limits or {})
    plan["limits"] = limits
    plan["key"] = sub.plan
    return plan


def has_feature(db: Session, org_id, feature: str) -> bool:
    return feature in effective_plan(db, org_id)["features"]


def require_feature(db: Session, org_id, feature: str):
    if not has_feature(db, org_id, feature):
        raise plan_limit(f"Your plan does not include '{feature.replace('_', ' ')}'. Upgrade to unlock it.", {"feature": feature})


def current_usage(db: Session, org_id, metric: str) -> int:
    if metric in MONTHLY_METRICS:
        v = db.scalar(select(UsageCounter.value).where(UsageCounter.org_id == org_id, UsageCounter.metric == metric,
                                                       UsageCounter.period == period_key()))
        return int(v or 0)
    counters = {
        "documents": lambda: db.scalar(select(func.count()).select_from(Document).where(Document.org_id == org_id)),
        "storage_mb": lambda: (db.scalar(select(func.coalesce(func.sum(Document.size_bytes), 0)).where(Document.org_id == org_id)) or 0) // (1024 * 1024),
        "agents": lambda: db.scalar(select(func.count()).select_from(Agent).where(Agent.org_id == org_id, Agent.status != "archived")),
        "workflows": lambda: db.scalar(select(func.count()).select_from(Workflow).where(Workflow.org_id == org_id, Workflow.status != "archived")),
        "datasets": lambda: db.scalar(select(func.count()).select_from(Dataset).where(Dataset.org_id == org_id)),
        "members": lambda: db.scalar(select(func.count()).select_from(Membership).where(Membership.org_id == org_id, Membership.status == "active")),
        "workspaces": lambda: db.scalar(select(func.count()).select_from(Workspace).where(Workspace.org_id == org_id)),
    }
    if metric == "integrations":
        from app.models import IntegrationConnection
        return int(db.scalar(select(func.count()).select_from(IntegrationConnection).where(
            IntegrationConnection.org_id == org_id, IntegrationConnection.status == "connected")) or 0)
    return int(counters[metric]() or 0)


def check_limit(db: Session, org_id, metric: str, increment: int = 1):
    limit = effective_plan(db, org_id)["limits"].get(metric, UNLIMITED)
    if limit == UNLIMITED:
        return
    used = current_usage(db, org_id, metric)
    if used + increment > limit:
        raise plan_limit(f"Plan limit reached for {metric.replace('_', ' ')} ({used}/{limit}). Upgrade your plan to continue.",
                         {"metric": metric, "used": used, "limit": limit})


def increment_usage(db: Session, org_id, metric: str, amount: int = 1):
    stmt = insert(UsageCounter).values(org_id=org_id, metric=metric, period=period_key(), value=amount)
    stmt = stmt.on_conflict_do_update(index_elements=["org_id", "metric", "period"], set_={"value": UsageCounter.value + amount})
    db.execute(stmt)


def usage_summary(db: Session, org_id) -> dict:
    plan = effective_plan(db, org_id)
    return {m: {"used": current_usage(db, org_id, m), "limit": lim} for m, lim in plan["limits"].items()}
