"""Module 3: Knowledge base & RAG."""
import hashlib
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, Form, UploadFile, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session
from app.core.audit import audit_ctx, track, outcome
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import OrgContext, require
from app.core.errors import not_found, bad_request, AppError
from app.core.permissions import ROLE_RANK, role_at_least
from app.core.plans import check_limit
from app.core.storage import get_storage, make_key
from app.models import Document, DocumentVersion, DocumentChunk, User
from app.modules.common import iso, user_brief
from app.rag.extraction import validate_file, ALLOWED
from app.rag.retrieval import hybrid_search, RetrievalFilters, assemble_context
from app.worker.queue import enqueue

router = APIRouter(prefix="/api/documents", tags=["knowledge"])
settings = get_settings()


def can_read(ctx: OrgContext, d: Document) -> bool:
    return role_at_least(ctx.role, d.min_role) or str(ctx.user.id) in (d.allowed_user_ids or [])


def doc_out(d: Document, uploader: User | None = None) -> dict:
    return {"id": str(d.id), "title": d.title, "filename": d.filename, "file_type": d.file_type, "size_bytes": d.size_bytes,
            "status": d.status, "error": d.error, "version": d.version, "min_role": d.min_role, "allowed_user_ids": d.allowed_user_ids,
            "tags": d.tags, "summary": d.summary, "page_count": d.page_count, "chunk_count": d.chunk_count,
            "chunking_strategy": d.chunking_strategy, "embedding_model": d.embedding_model, "injection_flags": d.injection_flags,
            "metadata": d.doc_metadata, "workspace_id": str(d.workspace_id) if d.workspace_id else None,
            "uploaded_by": user_brief(uploader), "created_at": iso(d.created_at), "updated_at": iso(d.updated_at), "indexed_at": iso(d.indexed_at)}


def get_doc(db: Session, ctx: OrgContext, doc_id) -> Document:
    d = db.get(Document, doc_id)
    if not d or d.org_id != ctx.org_id or d.deleted_at or not can_read(ctx, d):
        raise not_found("Document")
    return d


def create_document(db: Session, ctx: OrgContext, filename: str, data: bytes, *, title: str | None = None, tags: list[str] | None = None,
                    min_role: str = "viewer", chunking: str = "recursive", workspace_id=None) -> Document:
    ft = validate_file(filename, data, settings.max_upload_mb)
    check_limit(db, ctx.org_id, "documents")
    check_limit(db, ctx.org_id, "storage_mb", increment=max(1, len(data) // (1024 * 1024)))
    checksum = hashlib.sha256(data).hexdigest()
    dup = db.scalar(select(Document).where(Document.org_id == ctx.org_id, Document.checksum == checksum, Document.deleted_at.is_(None)))
    if dup:
        raise AppError(409, "duplicate_document", f"This file is already in your knowledge base as “{dup.title}”", {"document_id": str(dup.id)})
    key = make_key(ctx.org_id, "documents", filename)
    get_storage().put(key, data, ALLOWED[ft])
    d = Document(org_id=ctx.org_id, title=(title or filename.rsplit(".", 1)[0])[:300], filename=filename[:300], mime_type=ALLOWED[ft],
                 file_type=ft, size_bytes=len(data), storage_key=key, checksum=checksum, uploaded_by=ctx.user.id,
                 min_role=min_role if min_role in ROLE_RANK else "viewer", tags=tags or [], chunking_strategy=chunking,
                 workspace_id=workspace_id)
    db.add(d)
    db.flush()
    db.add(DocumentVersion(org_id=ctx.org_id, document_id=d.id, version=1, filename=filename, storage_key=key, checksum=checksum,
                           size_bytes=len(data), created_by=ctx.user.id))
    enqueue(db, "index_document", {"document_id": str(d.id)}, org_id=ctx.org_id)
    audit_ctx(db, ctx, "document.uploaded", "document", d.id, {"filename": filename, "size": len(data)})
    track(db, "document_uploaded", org_id=ctx.org_id, user_id=ctx.user.id, properties={"file_type": ft, "size_kb": len(data) // 1024})
    return d


@router.post("", status_code=201)
async def upload(file: UploadFile = File(...), title: str | None = Form(None), tags: str | None = Form(None),
                 min_role: str = Form("viewer"), chunking_strategy: str = Form("recursive"), workspace_id: str | None = Form(None),
                 ctx: OrgContext = Depends(require("documents.write")), db: Session = Depends(get_db)):
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if chunking_strategy not in ("recursive", "fixed", "sentence"):
        raise bad_request("Invalid chunking strategy")
    if ROLE_RANK.get(min_role, 0) > ROLE_RANK[ctx.role]:
        raise bad_request("You cannot restrict a document above your own role")
    d = create_document(db, ctx, file.filename or "upload.txt", data, title=title,
                        tags=[t.strip() for t in (tags or "").split(",") if t.strip()][:20], min_role=min_role, chunking=chunking_strategy,
                        workspace_id=uuid.UUID(workspace_id) if workspace_id else None)
    return doc_out(d, ctx.user)


@router.get("")
def list_documents(q: str | None = None, status: str | None = None, file_type: str | None = None, tag: str | None = None,
                   ctx: OrgContext = Depends(require("documents.read")), db: Session = Depends(get_db)):
    query = select(Document).where(Document.org_id == ctx.org_id, Document.deleted_at.is_(None))
    if q:
        query = query.where(Document.title.ilike(f"%{q}%"))
    if status:
        query = query.where(Document.status == status)
    if file_type:
        query = query.where(Document.file_type == file_type)
    rows = [d for d in db.scalars(query.order_by(Document.created_at.desc()).limit(500)) if can_read(ctx, d)]
    if tag:
        rows = [d for d in rows if tag in (d.tags or [])]
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({d.uploaded_by for d in rows if d.uploaded_by})))} if rows else {}
    return [doc_out(d, users.get(d.uploaded_by)) for d in rows]


@router.get("/stats")
def stats(ctx: OrgContext = Depends(require("documents.read")), db: Session = Depends(get_db)):
    rows = db.execute(select(Document.status, func.count()).where(Document.org_id == ctx.org_id, Document.deleted_at.is_(None))
                      .group_by(Document.status)).all()
    chunks = db.scalar(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.org_id == ctx.org_id))
    return {"by_status": {s: c for s, c in rows}, "chunks": chunks}


@router.get("/{doc_id}")
def get_document(doc_id: uuid.UUID, ctx: OrgContext = Depends(require("documents.read")), db: Session = Depends(get_db)):
    d = get_doc(db, ctx, doc_id)
    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == d.id, DocumentVersion.org_id == ctx.org_id)
                          .order_by(DocumentVersion.version.desc())).all()
    out = doc_out(d, db.get(User, d.uploaded_by) if d.uploaded_by else None)
    out["versions"] = [{"version": v.version, "filename": v.filename, "size_bytes": v.size_bytes, "created_at": iso(v.created_at)} for v in versions]
    return out


@router.get("/{doc_id}/chunks")
def get_chunks(doc_id: uuid.UUID, ctx: OrgContext = Depends(require("documents.read")), db: Session = Depends(get_db)):
    d = get_doc(db, ctx, doc_id)
    rows = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == d.id, DocumentChunk.org_id == ctx.org_id,
                                                  DocumentChunk.version == d.version).order_by(DocumentChunk.chunk_index)).all()
    return [{"id": str(c.id), "index": c.chunk_index, "content": c.content, "tokens": c.token_count, "page": c.page, "section": c.section,
             "injection_risk": c.injection_risk} for c in rows]


@router.get("/{doc_id}/download")
def download(doc_id: uuid.UUID, ctx: OrgContext = Depends(require("documents.read")), db: Session = Depends(get_db)):
    d = get_doc(db, ctx, doc_id)
    audit_ctx(db, ctx, "document.downloaded", "document", d.id)
    return Response(get_storage().get(d.storage_key), media_type=d.mime_type,
                    headers={"Content-Disposition": f'attachment; filename="{d.filename}"', "Content-Security-Policy": "sandbox"})


class DocUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    tags: list[str] | None = None
    min_role: str | None = None
    allowed_user_ids: list[str] | None = None


@router.patch("/{doc_id}")
def update_document(doc_id: uuid.UUID, body: DocUpdate, ctx: OrgContext = Depends(require("documents.write")), db: Session = Depends(get_db)):
    d = get_doc(db, ctx, doc_id)
    if body.title:
        d.title = body.title
    if body.tags is not None:
        d.tags = [t[:40] for t in body.tags][:20]
    if body.min_role is not None or body.allowed_user_ids is not None:
        if not ctx.can("documents.delete") and d.uploaded_by != ctx.user.id:
            raise AppError(403, "forbidden", "Only the uploader or a manager can change document permissions")
        if body.min_role:
            if body.min_role not in ROLE_RANK or ROLE_RANK[body.min_role] > ROLE_RANK[ctx.role]:
                raise bad_request("Invalid access level")
            d.min_role = body.min_role
        if body.allowed_user_ids is not None:
            d.allowed_user_ids = [str(uuid.UUID(x)) for x in body.allowed_user_ids][:100]
        audit_ctx(db, ctx, "document.permissions_changed", "document", d.id, {"min_role": d.min_role, "allowed": len(d.allowed_user_ids)})
    return doc_out(d)


@router.post("/{doc_id}/versions", status_code=201)
async def new_version(doc_id: uuid.UUID, file: UploadFile = File(...), ctx: OrgContext = Depends(require("documents.write")),
                      db: Session = Depends(get_db)):
    d = get_doc(db, ctx, doc_id)
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    ft = validate_file(file.filename or d.filename, data, settings.max_upload_mb)
    if ft != d.file_type:
        raise bad_request(f"New version must be a .{d.file_type} file")
    key = make_key(ctx.org_id, "documents", file.filename or d.filename)
    get_storage().put(key, data, d.mime_type)
    d.version += 1
    d.storage_key, d.checksum, d.size_bytes, d.filename = key, hashlib.sha256(data).hexdigest(), len(data), file.filename or d.filename
    d.status = "queued"
    db.add(DocumentVersion(org_id=ctx.org_id, document_id=d.id, version=d.version, filename=d.filename, storage_key=key,
                           checksum=d.checksum, size_bytes=len(data), created_by=ctx.user.id))
    enqueue(db, "index_document", {"document_id": str(d.id)}, org_id=ctx.org_id)
    audit_ctx(db, ctx, "document.version_uploaded", "document", d.id, {"version": d.version})
    return doc_out(d)


class ReindexIn(BaseModel):
    chunking_strategy: str | None = None


@router.post("/{doc_id}/reindex")
def reindex(doc_id: uuid.UUID, body: ReindexIn | None = None, ctx: OrgContext = Depends(require("documents.write")), db: Session = Depends(get_db)):
    d = get_doc(db, ctx, doc_id)
    if body and body.chunking_strategy:
        if body.chunking_strategy not in ("recursive", "fixed", "sentence"):
            raise bad_request("Invalid chunking strategy")
        d.chunking_strategy = body.chunking_strategy
    d.status = "queued"
    enqueue(db, "index_document", {"document_id": str(d.id)}, org_id=ctx.org_id)
    audit_ctx(db, ctx, "document.reindex_requested", "document", d.id)
    return doc_out(d)


@router.delete("/{doc_id}")
def delete_document(doc_id: uuid.UUID, ctx: OrgContext = Depends(require("documents.write")), db: Session = Depends(get_db)):
    d = get_doc(db, ctx, doc_id)
    if d.uploaded_by != ctx.user.id and not ctx.can("documents.delete"):
        raise AppError(403, "forbidden", "Only the uploader or a manager can delete this document")
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == d.id, DocumentChunk.org_id == ctx.org_id))
    for v in db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == d.id)):
        get_storage().delete(v.storage_key)
    d.deleted_at, d.status = datetime.now(timezone.utc), "deleted"
    audit_ctx(db, ctx, "document.deleted", "document", d.id, {"title": d.title})
    return {"ok": True}


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=25)
    mode: str = "hybrid"
    document_ids: list[str] | None = None
    file_types: list[str] | None = None
    tags: list[str] | None = None


@router.post("/search")
def search(body: SearchIn, ctx: OrgContext = Depends(require("documents.read")), db: Session = Depends(get_db)):
    if body.mode not in ("hybrid", "vector", "keyword"):
        raise bad_request("mode must be hybrid, vector or keyword")
    items = hybrid_search(db, org_id=ctx.org_id, user_id=ctx.user.id, role=ctx.role, query=body.query, top_k=body.top_k, mode=body.mode,
                          filters=RetrievalFilters(document_ids=body.document_ids, file_types=body.file_types, tags=body.tags))
    return [{"chunk_id": i.chunk_id, "document_id": i.document_id, "title": i.title, "page": i.page, "section": i.section,
             "content": i.content, "scores": {"vector": round(i.vector_score, 4), "keyword": round(i.keyword_score, 4),
                                              "fused": round(i.fused, 4), "rerank": i.rerank}, "injection_risk": i.injection_risk} for i in items]


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_ids: list[str] | None = None


@router.post("/ask")
def ask(body: AskIn, ctx: OrgContext = Depends(require("documents.read")), db: Session = Depends(get_db)):
    from app.modules.chat import answer_with_knowledge
    res = answer_with_knowledge(db, ctx, body.question, history=[], document_ids=body.document_ids, feature="rag")
    outcome(db, "knowledge_answer", org_id=ctx.org_id, user_id=ctx.user.id) if res["citations"] else None
    return res
