"""Module 2: AI Business Assistant (conversations, RAG answers, summarise/extract/report, sharing, export)."""
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session
from app.ai.catalog import catalog
from app.ai.gateway import generate, provider_status, AIUnavailable
from app.ai.providers.base import LLMRequest, ChatMessage
from app.ai.safety import validate_user_input, neutralize, UNTRUSTED_PREAMBLE
from app.ai.textutil import estimate_tokens, truncate_tokens
from app.core.audit import track, audit_ctx, outcome
from app.core.db import get_db
from app.core.deps import OrgContext, require
from app.core.errors import not_found, bad_request, AppError, forbidden
from app.core.plans import check_limit, increment_usage
from app.models import Conversation, ConversationShare, Message, Document, Membership, User
from app.modules.common import iso, user_brief
from app.modules.notifications import notify
from app.rag.retrieval import hybrid_search, assemble_context, verify_citations, RetrievalFilters

router = APIRouter(prefix="/api/conversations", tags=["assistant"])
assistant_router = APIRouter(prefix="/api/assistant", tags=["assistant"])
ROUTERS = [router, assistant_router]
HISTORY_TOKEN_BUDGET = 6000


def system_prompt(org_name: str) -> str:
    return (f"You are NEXORA, the AI business operations assistant for {org_name}. Be accurate, concise and practical. "
            "Use Markdown. When the user's question can be answered from retrieved knowledge, ground your answer in it and cite "
            "sources inline as [n] immediately after the supported claim. If the knowledge does not contain the answer, say so plainly "
            "instead of guessing. Never invent figures, customers or citations. " + UNTRUSTED_PREAMBLE)


def _history(db: Session, conv: Conversation | None) -> list[ChatMessage]:
    if not conv:
        return []
    msgs = db.scalars(select(Message).where(Message.conversation_id == conv.id, Message.org_id == conv.org_id)
                      .order_by(Message.created_at.desc()).limit(30)).all()
    out, used = [], 0
    for m in msgs:  # newest first; keep within token budget (context truncation)
        t = estimate_tokens(m.content)
        if used + t > HISTORY_TOKEN_BUDGET:
            break
        used += t
        out.insert(0, ChatMessage(role=m.role, content=m.content))
    return out


def answer_with_knowledge(db: Session, ctx: OrgContext, question: str, history: list[ChatMessage], document_ids=None,
                          feature: str = "chat", task_type: str = "chat", preference: str | None = None, use_knowledge: bool = True) -> dict:
    items = []
    if use_knowledge:
        items = hybrid_search(db, org_id=ctx.org_id, user_id=ctx.user.id, role=ctx.role, query=question, top_k=6,
                              filters=RetrievalFilters(document_ids=document_ids) if document_ids else None)
    assembled = assemble_context(items)
    user_content = question if not assembled.prompt_block else f"{assembled.prompt_block}\n\nUser question: {question}"
    req = LLMRequest(messages=history + [ChatMessage(role="user", content=user_content)], system=system_prompt(ctx.org.name),
                     task_type=task_type, max_tokens=catalog()["routes"][task_type]["max_tokens"],
                     metadata={"context": assembled.chunks_for_demo, "question": question})
    resp = generate(db, req, org_id=ctx.org_id, user_id=ctx.user.id, feature=feature, preference=preference)
    clean, cites, cstats = verify_citations(resp.text, assembled.citations)
    meta = {"model": resp.model, "provider": resp.provider, "input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens,
            "cached_tokens": resp.cached_tokens, "demo": resp.demo, "refusal": resp.refusal, "retrieved": len(items), "citation_stats": cstats,
            **getattr(resp, "meta", {})}
    return {"answer": clean, "citations": cites, "meta": meta}


def conv_access(db: Session, ctx: OrgContext, conv_id, write: bool = False) -> Conversation:
    c = db.get(Conversation, conv_id)
    if not c or c.org_id != ctx.org_id:
        raise not_found("Conversation")
    if c.user_id == ctx.user.id:
        return c
    share = db.scalar(select(ConversationShare).where(ConversationShare.conversation_id == c.id, ConversationShare.user_id == ctx.user.id,
                                                      ConversationShare.org_id == ctx.org_id))
    if not share:
        raise not_found("Conversation")
    if write:
        raise forbidden("This conversation was shared with you as read-only")
    return c


def conv_out(c: Conversation, user_id) -> dict:
    return {"id": str(c.id), "title": c.title, "model_route": c.model_route, "use_knowledge": c.use_knowledge, "archived": c.archived,
            "owner_id": str(c.user_id), "is_owner": c.user_id == user_id, "created_at": iso(c.created_at), "updated_at": iso(c.updated_at)}


def msg_out(m: Message) -> dict:
    return {"id": str(m.id), "role": m.role, "content": m.content, "citations": m.citations, "attachments": m.attachments, "meta": m.meta,
            "feedback": m.feedback, "created_at": iso(m.created_at)}


class ConvIn(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    model_route: str = "auto"
    use_knowledge: bool = True


class ConvUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    model_route: str | None = None
    use_knowledge: bool | None = None
    archived: bool | None = None


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=32000)
    document_ids: list[str] | None = None
    mode: str = "auto"  # auto | analysis | report


VALID_ROUTES = {"auto", "fast", "balanced", "frontier"} | set(catalog()["models"].keys())


@router.get("")
def list_conversations(ctx: OrgContext = Depends(require("chat.use")), db: Session = Depends(get_db)):
    shared_ids = select(ConversationShare.conversation_id).where(ConversationShare.user_id == ctx.user.id, ConversationShare.org_id == ctx.org_id)
    rows = db.scalars(select(Conversation).where(Conversation.org_id == ctx.org_id,
                                                 or_(Conversation.user_id == ctx.user.id, Conversation.id.in_(shared_ids)))
                      .order_by(Conversation.updated_at.desc()).limit(200)).all()
    return [conv_out(c, ctx.user.id) for c in rows]


@router.post("", status_code=201)
def create_conversation(body: ConvIn, ctx: OrgContext = Depends(require("chat.use")), db: Session = Depends(get_db)):
    if body.model_route not in VALID_ROUTES:
        raise bad_request("Unknown model route")
    c = Conversation(org_id=ctx.org_id, user_id=ctx.user.id, title=body.title or "New conversation", model_route=body.model_route,
                     use_knowledge=body.use_knowledge)
    db.add(c)
    db.flush()
    return conv_out(c, ctx.user.id)


@router.get("/{conv_id}")
def get_conversation(conv_id: uuid.UUID, ctx: OrgContext = Depends(require("chat.use")), db: Session = Depends(get_db)):
    c = conv_access(db, ctx, conv_id)
    msgs = db.scalars(select(Message).where(Message.conversation_id == c.id, Message.org_id == ctx.org_id).order_by(Message.created_at)).all()
    shares = db.scalars(select(ConversationShare).where(ConversationShare.conversation_id == c.id)).all()
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_([s.user_id for s in shares])))} if shares else {}
    return {**conv_out(c, ctx.user.id), "messages": [msg_out(m) for m in msgs],
            "shares": [{"user": user_brief(users.get(s.user_id)), "permission": s.permission} for s in shares]}


@router.patch("/{conv_id}")
def update_conversation(conv_id: uuid.UUID, body: ConvUpdate, ctx: OrgContext = Depends(require("chat.use")), db: Session = Depends(get_db)):
    c = conv_access(db, ctx, conv_id, write=True)
    if body.model_route and body.model_route not in VALID_ROUTES:
        raise bad_request("Unknown model route")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(c, k, v)
    return conv_out(c, ctx.user.id)


@router.delete("/{conv_id}")
def delete_conversation(conv_id: uuid.UUID, ctx: OrgContext = Depends(require("chat.use")), db: Session = Depends(get_db)):
    c = conv_access(db, ctx, conv_id, write=True)
    db.delete(c)
    return {"ok": True}


@router.post("/{conv_id}/messages")
def send_message(conv_id: uuid.UUID, body: MessageIn, ctx: OrgContext = Depends(require("chat.use")), db: Session = Depends(get_db)):
    c = conv_access(db, ctx, conv_id, write=True)
    content = validate_user_input(body.content)
    check_limit(db, ctx.org_id, "ai_messages")
    history = _history(db, c)
    user_msg = Message(org_id=ctx.org_id, conversation_id=c.id, role="user", content=content,
                       attachments=[{"document_id": d} for d in (body.document_ids or [])])
    db.add(user_msg)
    track(db, "ai_query_submitted", org_id=ctx.org_id, user_id=ctx.user.id, properties={"mode": body.mode, "knowledge": c.use_knowledge})
    task_type = "analysis" if body.mode in ("analysis", "report") or c.model_route == "frontier" else "chat"
    pref = None if c.model_route == "auto" else c.model_route
    question = content if body.mode != "report" else f"Write a structured business report (executive summary, findings, recommendations) about: {content}"
    try:
        res = answer_with_knowledge(db, ctx, question, history, document_ids=body.document_ids, task_type=task_type, preference=pref,
                                    use_knowledge=c.use_knowledge)
    except AIUnavailable as e:
        track(db, "ai_query_failed", org_id=ctx.org_id, user_id=ctx.user.id)
        db.commit()
        raise AppError(503, "ai_unavailable", "The AI service is temporarily unavailable. Please retry.", {"reason": str(e)[:300]})
    increment_usage(db, ctx.org_id, "ai_messages")
    asst = Message(org_id=ctx.org_id, conversation_id=c.id, role="assistant", content=res["answer"], citations=res["citations"], meta=res["meta"])
    db.add(asst)
    if c.title == "New conversation":
        c.title = (content[:60] + ("…" if len(content) > 60 else "")).replace("\n", " ")
    c.updated_at = datetime.now(timezone.utc)
    track(db, "ai_query_completed", org_id=ctx.org_id, user_id=ctx.user.id,
          properties={"model": res["meta"]["model"], "citations": len(res["citations"]), "latency_ms": res["meta"].get("latency_ms"),
                      "demo": res["meta"]["demo"]})
    if body.mode == "report":
        track(db, "report_generated", org_id=ctx.org_id, user_id=ctx.user.id)
        outcome(db, "report_generated", org_id=ctx.org_id, user_id=ctx.user.id)
    db.flush()
    return {"user_message": msg_out(user_msg), "assistant_message": msg_out(asst)}


@router.post("/{conv_id}/attachments", status_code=201)
async def attach(conv_id: uuid.UUID, file: UploadFile = File(...), ctx: OrgContext = Depends(require("documents.write")),
                 db: Session = Depends(get_db)):
    conv_access(db, ctx, conv_id, write=True)
    from app.modules.knowledge import create_document, doc_out
    from app.core.config import get_settings
    data = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    d = create_document(db, ctx, file.filename or "upload.txt", data, tags=["chat-upload"])
    return doc_out(d, ctx.user)


class ShareIn(BaseModel):
    user_ids: list[str]
    permission: str = "view"


@router.post("/{conv_id}/share")
def share(conv_id: uuid.UUID, body: ShareIn, ctx: OrgContext = Depends(require("chat.use")), db: Session = Depends(get_db)):
    c = conv_access(db, ctx, conv_id, write=True)
    if c.user_id != ctx.user.id:
        raise forbidden("Only the owner can share this conversation")
    if body.permission not in ("view", "comment"):
        raise bad_request("Invalid permission")
    added = 0
    for uid in body.user_ids[:50]:
        u = uuid.UUID(uid)
        m = db.scalar(select(Membership).where(Membership.org_id == ctx.org_id, Membership.user_id == u, Membership.status == "active"))
        if not m:
            raise bad_request("You can only share with active members of this organisation")
        if not db.scalar(select(ConversationShare).where(ConversationShare.conversation_id == c.id, ConversationShare.user_id == u)):
            db.add(ConversationShare(org_id=ctx.org_id, conversation_id=c.id, user_id=u, permission=body.permission))
            notify(db, ctx.org_id, u, "mention", f"{ctx.user.full_name} shared a conversation: {c.title}", link=f"/app/assistant/{c.id}")
            added += 1
    audit_ctx(db, ctx, "conversation.shared", "conversation", c.id, {"users": len(body.user_ids)})
    track(db, "conversation_shared", org_id=ctx.org_id, user_id=ctx.user.id, properties={"count": added})
    return {"ok": True, "added": added}


@router.delete("/{conv_id}/share/{user_id}")
def unshare(conv_id: uuid.UUID, user_id: uuid.UUID, ctx: OrgContext = Depends(require("chat.use")), db: Session = Depends(get_db)):
    c = conv_access(db, ctx, conv_id, write=True)
    s = db.scalar(select(ConversationShare).where(ConversationShare.conversation_id == c.id, ConversationShare.user_id == user_id))
    if s:
        db.delete(s)
    return {"ok": True}


@router.get("/{conv_id}/export")
def export(conv_id: uuid.UUID, format: str = "md", ctx: OrgContext = Depends(require("chat.use")), db: Session = Depends(get_db)):
    c = conv_access(db, ctx, conv_id)
    msgs = db.scalars(select(Message).where(Message.conversation_id == c.id, Message.org_id == ctx.org_id).order_by(Message.created_at)).all()
    track(db, "response_exported", org_id=ctx.org_id, user_id=ctx.user.id, properties={"format": format})
    if format == "json":
        return {"conversation": conv_out(c, ctx.user.id), "messages": [msg_out(m) for m in msgs]}
    lines = [f"# {c.title}", f"_Exported from NEXORA AI on {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}_", ""]
    for m in msgs:
        lines.append(f"## {'You' if m.role == 'user' else 'NEXORA'}\n\n{m.content}\n")
        for ct in m.citations or []:
            lines.append(f"- [{ct['n']}] {ct['title']}" + (f", p.{ct['page']}" if ct.get("page") else ""))
    return PlainTextResponse("\n".join(lines), media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="conversation-{c.id.hex[:8]}.md"'})


class FeedbackIn(BaseModel):
    value: int = Field(ge=-1, le=1)


@router.post("/messages/{msg_id}/feedback")
def feedback(msg_id: uuid.UUID, body: FeedbackIn, ctx: OrgContext = Depends(require("chat.use")), db: Session = Depends(get_db)):
    m = db.get(Message, msg_id)
    if not m or m.org_id != ctx.org_id:
        raise not_found("Message")
    conv_access(db, ctx, m.conversation_id)
    m.feedback = body.value or None
    return {"ok": True}


# ---------------- task-specific assistant endpoints ----------------
def _doc_text(db: Session, ctx: OrgContext, document_id: str) -> tuple[Document, str]:
    from app.modules.knowledge import get_doc
    from app.models import DocumentChunk
    d = get_doc(db, ctx, uuid.UUID(document_id))
    if d.status != "indexed":
        raise bad_request("Document is not indexed yet")
    chunks = db.scalars(select(DocumentChunk.content).where(DocumentChunk.document_id == d.id, DocumentChunk.org_id == ctx.org_id,
                                                            DocumentChunk.version == d.version).order_by(DocumentChunk.chunk_index)).all()
    return d, "\n\n".join(chunks)


class SummarizeIn(BaseModel):
    document_id: str | None = None
    text: str | None = Field(default=None, max_length=100_000)
    length: str = "short"  # short | detailed


def _meta(resp) -> dict:
    return {"model": resp.model, "provider": resp.provider, "demo": resp.demo, "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens, **getattr(resp, "meta", {})}


@assistant_router.post("/summarize")
def summarize(body: SummarizeIn, ctx: OrgContext = Depends(require("chat.use")), db: Session = Depends(get_db)):
    if body.document_id:
        d, text = _doc_text(db, ctx, body.document_id)
    elif body.text:
        text = body.text
    else:
        raise bad_request("Provide document_id or text")
    check_limit(db, ctx.org_id, "ai_messages")
    text = neutralize(truncate_tokens(text, 30000))
    task = "summarize" if body.length == "short" else "analysis"
    resp = generate(db, LLMRequest(messages=[ChatMessage(role="user", content=f"<document>\n{text}\n</document>\n\n"
                                                         f"Write a {'concise 5-bullet' if body.length == 'short' else 'detailed sectioned'} summary.")],
                                   system="You summarise business documents faithfully. " + UNTRUSTED_PREAMBLE, task_type=task,
                                   metadata={"demo_handler": "summarize", "text": text}),
                    org_id=ctx.org_id, user_id=ctx.user.id, feature="chat")
    increment_usage(db, ctx.org_id, "ai_messages")
    outcome(db, "document_summarised", org_id=ctx.org_id, user_id=ctx.user.id)
    return {"summary": resp.text, "meta": _meta(resp)}


class FieldSpec(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,40}$")
    type: str = "string"  # string | number | integer | boolean | date | list
    description: str = ""


class ExtractIn(BaseModel):
    document_id: str | None = None
    text: str | None = Field(default=None, max_length=100_000)
    fields: list[FieldSpec] = Field(min_length=1, max_length=30)


def schema_from_fields(fields: list[FieldSpec]) -> dict:
    props = {}
    for f in fields:
        t = {"date": "string", "list": "array"}.get(f.type, f.type if f.type in ("string", "number", "integer", "boolean") else "string")
        p = {"type": t, "description": f.description or f.name}
        if t == "array":
            p["items"] = {"type": "string"}
        props[f.name] = p
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


@assistant_router.post("/extract")
def extract_structured(body: ExtractIn, ctx: OrgContext = Depends(require("chat.use")), db: Session = Depends(get_db)):
    text = _doc_text(db, ctx, body.document_id)[1] if body.document_id else (body.text or "")
    if not text.strip():
        raise bad_request("Provide document_id or text")
    check_limit(db, ctx.org_id, "ai_messages")
    schema = schema_from_fields(body.fields)
    text = neutralize(truncate_tokens(text, 30000))
    resp = generate(db, LLMRequest(messages=[ChatMessage(role="user", content=f"<document>\n{text}\n</document>\n\nExtract the requested fields. "
                                                         "Use empty values when a field is not present; never guess.")],
                                   system="You extract structured data from business documents. " + UNTRUSTED_PREAMBLE, task_type="extract",
                                   json_schema=schema, metadata={"text": text}),
                    org_id=ctx.org_id, user_id=ctx.user.id, feature="chat")
    increment_usage(db, ctx.org_id, "ai_messages")
    if resp.parsed is None:
        raise AppError(502, "invalid_model_output", "The model did not return valid structured data. Please retry.")
    outcome(db, "data_extracted", org_id=ctx.org_id, user_id=ctx.user.id)
    return {"data": resp.parsed, "schema": schema, "meta": _meta(resp)}


class RecommendIn(BaseModel):
    conversation_id: str | None = None
    text: str | None = Field(default=None, max_length=50_000)


TASKS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["tasks"], "properties": {"tasks": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["title", "description", "owner_name", "due_date", "priority"],
    "properties": {"title": {"type": "string"}, "description": {"type": "string"}, "owner_name": {"type": ["string", "null"]},
                   "due_date": {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD if stated"},
                   "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]}}}}}}


def extract_tasks_ai(db: Session, ctx_org_id, user_id, text: str, feature: str = "tasks") -> tuple[list[dict], dict]:
    text = neutralize(truncate_tokens(text, 20000))
    resp = generate(db, LLMRequest(messages=[ChatMessage(role="user", content=f"<document>\n{text}\n</document>\n\nToday is {datetime.now(timezone.utc):%Y-%m-%d}. "
                                                         "List every concrete action item. Only include tasks that are explicitly stated or clearly implied.")],
                                   system="You convert meeting notes and business conversations into actionable tasks. " + UNTRUSTED_PREAMBLE,
                                   task_type="extract", json_schema=TASKS_SCHEMA, metadata={"demo_handler": "extract_tasks", "text": text}),
                    org_id=ctx_org_id, user_id=user_id, feature=feature)
    tasks = (resp.parsed or {}).get("tasks", [])
    return tasks, _meta(resp)


@assistant_router.post("/recommend-tasks")
def recommend_tasks(body: RecommendIn, ctx: OrgContext = Depends(require("chat.use")), db: Session = Depends(get_db)):
    text = body.text or ""
    if body.conversation_id:
        c = conv_access(db, ctx, uuid.UUID(body.conversation_id))
        msgs = db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at)).all()
        text = "\n".join(f"{m.role}: {m.content}" for m in msgs)
    if not text.strip():
        raise bad_request("Nothing to analyse")
    check_limit(db, ctx.org_id, "ai_messages")
    tasks, meta = extract_tasks_ai(db, ctx.org_id, ctx.user.id, text)
    increment_usage(db, ctx.org_id, "ai_messages")
    return {"suggestions": tasks, "meta": meta}


@assistant_router.get("/models")
def models(ctx: OrgContext = Depends(require("chat.use"))):
    cat = catalog()
    st = provider_status()
    return {"providers": st, "routes": {k: {"candidates": v["candidates"], "why": v["why"]} for k, v in cat["routes"].items()},
            "models": [{"id": k, **{kk: vv for kk, vv in v.items()}, "available": st.get(v["provider"], False) or v["provider"] == "demo"}
                       for k, v in cat["models"].items()],
            "selectable": ["auto", "fast", "balanced", "frontier"]}
