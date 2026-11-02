"""Experimentation: deterministic assignment + exposure tracking. Results are computed from events; nothing is pre-filled."""
import hashlib
from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.core.audit import track
from app.core.db import get_db
from app.core.deps import OrgContext, get_org_context, require_super_admin
from app.core.errors import not_found
from app.models import ExperimentAssignment, User

router = APIRouter(prefix="/api/experiments", tags=["experiments"])

EXPERIMENTS = {
    "onboarding_flow": {"unit": "user", "variants": ["short", "guided"], "metric": "outcome_achieved within 24h", "status": "running"},
    "assistant_starter_prompts": {"unit": "user", "variants": ["none", "role_based"], "metric": "ai_query_completed in first session", "status": "running"},
    "kb_upload_experience": {"unit": "user", "variants": ["standard", "sample_docs"], "metric": "document_indexed within 24h", "status": "running"},
    "free_tier_limits": {"unit": "org", "variants": ["150_messages", "300_messages"], "metric": "free-to-paid conversion 30d", "status": "draft"},
    "pricing_page": {"unit": "visitor", "variants": ["monthly_default", "annual_default"], "metric": "subscription_started", "status": "draft"},
    "ai_workflow_suggestions": {"unit": "org", "variants": ["off", "on"], "metric": "workflow_published within 7d", "status": "draft"},
}


def assign(db: Session, key: str, subject_id: str) -> str:
    exp = EXPERIMENTS[key]
    existing = db.scalar(select(ExperimentAssignment).where(ExperimentAssignment.experiment_key == key, ExperimentAssignment.subject_id == subject_id))
    if existing:
        return existing.variant
    h = int(hashlib.sha256(f"{key}:{subject_id}".encode()).hexdigest()[:8], 16)
    variant = exp["variants"][h % len(exp["variants"])]
    db.add(ExperimentAssignment(experiment_key=key, subject_id=subject_id, variant=variant))
    return variant


@router.get("/assignments")
def assignments(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    out = {}
    for k, e in EXPERIMENTS.items():
        if e["status"] != "running" or e["unit"] == "visitor":
            continue
        subject = str(ctx.user.id) if e["unit"] == "user" else str(ctx.org_id)
        out[k] = assign(db, k, subject)
    return out


@router.post("/{key}/exposure")
def exposure(key: str, ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    if key not in EXPERIMENTS:
        raise not_found("Experiment")
    e = EXPERIMENTS[key]
    variant = assign(db, key, str(ctx.user.id) if e["unit"] == "user" else str(ctx.org_id))
    track(db, "experiment_exposed", org_id=ctx.org_id, user_id=ctx.user.id, properties={"experiment": key, "variant": variant})
    return {"variant": variant}


@router.get("/results")
def results(admin: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    rows = db.execute(text("""SELECT experiment_key, variant, count(*) FROM experiment_assignments GROUP BY 1, 2""")).all()
    out = {k: {"config": v, "assignments": {}} for k, v in EXPERIMENTS.items()}
    for k, var, c in rows:
        if k in out:
            out[k]["assignments"][var] = c
    return {"experiments": out, "note": "Only assignment counts are reported automatically; outcome analysis uses database/analytics_views.sql. "
                                        "No experiment has been run with real users."}
