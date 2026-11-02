"""Background indexing pipeline: extract -> sanitize/flag -> chunk -> embed -> store -> summarise -> notify/trigger."""
import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.ai.safety import injection_risk
from app.core.audit import track
from app.core.storage import get_storage
from app.models import Document, DocumentChunk, Job, Membership
from app.rag.chunking import chunk_sections
from app.rag.embeddings import get_embedder
from app.rag.extraction import extract
from app.worker.queue import handler

log = logging.getLogger("nexora.indexing")


def index_document(db: Session, doc: Document) -> Document:
    doc.status, doc.error = "processing", None
    db.flush()
    data = get_storage().get(doc.storage_key)
    ex = extract(doc.file_type, data)
    if not ex.full_text.strip():
        raise ValueError("No extractable text found" + (f" ({'; '.join(ex.warnings[:2])})" if ex.warnings else ""))
    chunks = chunk_sections(ex.sections, doc.chunking_strategy)
    emb = get_embedder()
    vectors = emb.embed([((c.section or "") + "\n" + c.content) for c in chunks])
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id, DocumentChunk.org_id == doc.org_id))
    flags = 0
    for c, v in zip(chunks, vectors):
        risk = injection_risk(c.content)
        flags += risk >= 0.6
        db.add(DocumentChunk(org_id=doc.org_id, document_id=doc.id, version=doc.version, chunk_index=c.index, content=c.content,
                             token_count=c.tokens, page=c.page, section=c.section, embedding=v, embedding_model=emb.model,
                             injection_risk=risk, meta={"strategy": doc.chunking_strategy}))
    doc.chunk_count, doc.page_count, doc.injection_flags = len(chunks), ex.page_count, flags
    doc.doc_metadata = {**(doc.doc_metadata or {}), **{k: v for k, v in ex.metadata.items() if isinstance(v, (str, int, float, list))},
                        "warnings": ex.warnings, "characters": len(ex.full_text)}
    doc.embedding_model = emb.model
    try:
        from app.ai.gateway import generate
        from app.ai.providers.base import LLMRequest, ChatMessage
        from app.ai.safety import UNTRUSTED_PREAMBLE, neutralize
        sample = neutralize(ex.full_text[:12000])
        resp = generate(db, LLMRequest(messages=[ChatMessage(role="user", content=f"<document>\n{sample}\n</document>\n\nSummarise this document in 3-5 bullet points.")],
                                       system="You summarise business documents accurately and concisely. " + UNTRUSTED_PREAMBLE,
                                       task_type="summarize", metadata={"demo_handler": "summarize", "text": sample}),
                        org_id=doc.org_id, user_id=doc.uploaded_by, feature="rag")
        doc.summary = resp.text
    except Exception as e:  # summary is best-effort; indexing must still succeed
        log.warning("summary failed for %s: %s", doc.id, e)
    doc.status, doc.indexed_at = "indexed", datetime.now(timezone.utc)
    track(db, "document_indexed", org_id=doc.org_id, user_id=doc.uploaded_by,
          properties={"file_type": doc.file_type, "chunks": len(chunks), "injection_flags": flags})
    return doc


@handler("index_document")
def handle_index(db: Session, job: Job):
    doc = db.get(Document, uuid.UUID(job.payload["document_id"]))
    if not doc or doc.org_id != job.org_id or doc.deleted_at:
        return
    from app.modules.notifications import notify
    try:
        index_document(db, doc)
        db.flush()
        notify(db, doc.org_id, doc.uploaded_by, "document", f"“{doc.title}” is indexed and searchable",
               f"{doc.chunk_count} chunks" + (f", {doc.injection_flags} flagged for suspicious instructions" if doc.injection_flags else ""),
               link=f"/app/knowledge/{doc.id}")
        from app.workflows.service import fire_event_trigger
        fire_event_trigger(db, doc.org_id, "document_uploaded", {"document_id": str(doc.id), "title": doc.title, "file_type": doc.file_type,
                                                                 "summary": doc.summary or ""})
    except Exception as e:
        db.rollback()
        doc = db.get(Document, doc.id)
        doc.status, doc.error = "failed", str(getattr(e, "detail", None) or e)[:500]
        track(db, "document_index_failed", org_id=doc.org_id, user_id=doc.uploaded_by, properties={"error": doc.error[:100]})
        notify(db, doc.org_id, doc.uploaded_by, "document", f"Indexing failed for “{doc.title}”", doc.error, link=f"/app/knowledge/{doc.id}")
        db.commit()
