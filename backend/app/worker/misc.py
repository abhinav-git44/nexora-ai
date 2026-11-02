"""Misc job handlers: Mixpanel forwarding, organisation purge."""
import base64
import json
import uuid
from datetime import datetime, timezone
import httpx
from sqlalchemy import select, text, delete
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.storage import get_storage
from app.models import Job, Organization, Document, DocumentVersion, Dataset
from app.worker.queue import handler


@handler("mixpanel_forward")
def mixpanel_forward(db: Session, job: Job):
    token = get_settings().mixpanel_token
    if not token:
        return
    p = job.payload
    event = {"event": p["event"], "properties": {"token": token, "distinct_id": p.get("distinct_id") or p.get("org_id") or "anonymous",
                                                 "$insert_id": p["insert_id"], "org_id": p.get("org_id"), "$groups": {"org_id": p.get("org_id")},
                                                 **(p.get("properties") or {})}}
    data = base64.b64encode(json.dumps([event]).encode()).decode()
    r = httpx.post("https://api.mixpanel.com/track", data={"data": data}, timeout=10)
    r.raise_for_status()


@handler("purge_org")
def purge_org(db: Session, job: Job):
    org = db.get(Organization, uuid.UUID(job.payload["org_id"]))
    if not org or not org.deletion_requested_at:
        return  # cancelled
    st = get_storage()
    for v in db.scalars(select(DocumentVersion).where(DocumentVersion.org_id == org.id)):
        st.delete(v.storage_key)
    for d in db.scalars(select(Dataset).where(Dataset.org_id == org.id)):
        db.execute(text(f'DROP TABLE IF EXISTS datasets."{d.table_name}"'))
    org.deleted_at = datetime.now(timezone.utc)
    org.name = f"Deleted organisation {org.id.hex[:8]}"
    # Cascading FKs remove all tenant rows.
    db.execute(delete(Organization).where(Organization.id == org.id))
