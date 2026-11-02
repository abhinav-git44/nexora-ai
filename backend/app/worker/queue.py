"""Postgres-backed job queue + scheduler. Runs in-process (dev) or as `python -m app.worker.run` (production)."""
import logging
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.db import SessionLocal
from app.models import Job

log = logging.getLogger("nexora.worker")
HANDLERS: dict = {}


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def enqueue(db: Session, kind: str, payload: dict, org_id=None, delay_s: int = 0, max_attempts: int = 3) -> Job:
    job = Job(kind=kind, payload=payload, org_id=org_id, max_attempts=max_attempts,
              run_after=datetime.now(timezone.utc) + timedelta(seconds=delay_s))
    db.add(job)
    db.flush()
    return job


def _claim(db: Session) -> Job | None:
    stale = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.execute(update(Job).where(Job.status == "running", Job.locked_at < stale).values(status="queued"))
    job = db.scalar(select(Job).where(Job.status == "queued", Job.run_after <= datetime.now(timezone.utc))
                    .order_by(Job.run_after).limit(1).with_for_update(skip_locked=True))
    if job:
        job.status, job.locked_at, job.attempts = "running", datetime.now(timezone.utc), job.attempts + 1
        db.commit()
    return job


def run_job(job_id) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        fn = HANDLERS.get(job.kind)
        try:
            if not fn:
                raise RuntimeError(f"No handler for job kind {job.kind}")
            fn(db, job)
            job.status, job.finished_at, job.last_error = "succeeded", datetime.now(timezone.utc), None
            db.commit()
        except Exception as e:
            db.rollback()
            job = db.get(Job, job_id)
            job.last_error = f"{e}\n{traceback.format_exc()[-1500:]}"
            if job.attempts >= job.max_attempts:
                job.status, job.finished_at = "failed", datetime.now(timezone.utc)
                log.error("Job %s (%s) failed permanently: %s", job.id, job.kind, e)
            else:
                job.status = "queued"
                job.run_after = datetime.now(timezone.utc) + timedelta(seconds=2 ** job.attempts * 5)
            db.commit()


def run_pending(max_jobs: int = 100) -> int:
    """Drain due jobs synchronously (used by tests, CLI and the worker loop)."""
    n = 0
    while n < max_jobs:
        with SessionLocal() as db:
            job = _claim(db)
            if not job:
                break
            jid = job.id
        run_job(jid)
        n += 1
    return n


def scheduler_tick():
    from app.workflows.service import enqueue_due_scheduled
    with SessionLocal() as db:
        enqueue_due_scheduled(db)
        db.commit()


_stop = threading.Event()


def loop(poll_s: float = 1.0):
    import app.worker.tasks  # noqa: F401  register handlers
    last_sched = 0.0
    while not _stop.is_set():
        try:
            if time.time() - last_sched > 15:
                scheduler_tick()
                last_sched = time.time()
            if run_pending(20) == 0:
                _stop.wait(poll_s)
        except Exception:
            log.exception("worker loop error")
            _stop.wait(5)


def start_background():
    t = threading.Thread(target=loop, name="nexora-worker", daemon=True)
    t.start()
    return t


def stop_background():
    _stop.set()
