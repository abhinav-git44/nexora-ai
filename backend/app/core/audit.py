import logging
import uuid
from sqlalchemy.orm import Session
from app.models import AuditLog, AnalyticsEvent, Job

log = logging.getLogger("nexora.audit")


def audit(db: Session, action: str, *, org_id=None, actor_id=None, target_type=None, target_id=None, details=None, ip=None):
    db.add(AuditLog(org_id=org_id, actor_id=actor_id, action=action, target_type=target_type,
                    target_id=str(target_id) if target_id else None, details=details or {}, ip=ip))


def audit_ctx(db: Session, ctx, action: str, target_type=None, target_id=None, details=None):
    audit(db, action, org_id=ctx.org_id, actor_id=ctx.user.id, target_type=target_type, target_id=target_id, details=details, ip=ctx.ip)


# --- Product analytics (Mixpanel-compatible taxonomy; see docs/ANALYTICS_FRAMEWORK.md) ---
EVENTS = {
    "user_signed_up", "user_logged_in", "email_verified", "workspace_created", "org_created", "member_invited", "invitation_accepted",
    "onboarding_completed", "document_uploaded", "document_indexed", "document_index_failed", "ai_query_submitted", "ai_query_completed",
    "ai_query_failed", "agent_created", "agent_executed", "agent_run_succeeded", "agent_run_failed", "workflow_created", "workflow_published",
    "workflow_executed", "workflow_completed", "workflow_failed", "dataset_uploaded", "dataset_queried", "task_created", "task_completed",
    "tasks_extracted_by_ai", "subscription_started", "subscription_upgraded", "subscription_downgraded", "subscription_canceled",
    "integration_connected", "integration_disconnected", "approval_decided", "conversation_shared", "response_exported", "report_generated",
    "outcome_achieved", "experiment_exposed",
}


def track(db: Session, event: str, *, org_id=None, user_id=None, properties: dict | None = None):
    if event not in EVENTS:
        log.warning("Untracked event name %s (add to taxonomy)", event)
    props = properties or {}
    db.add(AnalyticsEvent(org_id=org_id, user_id=user_id, event=event, properties=props))
    from app.core.config import get_settings
    if get_settings().mixpanel_token:
        db.add(Job(org_id=org_id, kind="mixpanel_forward", payload={
            "event": event, "distinct_id": str(user_id) if user_id else None, "org_id": str(org_id) if org_id else None, "properties": props,
            "insert_id": uuid.uuid4().hex}))


def outcome(db: Session, kind: str, *, org_id, user_id=None, properties: dict | None = None):
    """North Star: a completed, user-valuable action (see ANALYTICS_FRAMEWORK.md for the definition)."""
    track(db, "outcome_achieved", org_id=org_id, user_id=user_id, properties={"outcome_type": kind, **(properties or {})})
