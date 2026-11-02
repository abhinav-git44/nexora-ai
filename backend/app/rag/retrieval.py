"""Hybrid retrieval: pgvector cosine + Postgres full-text, fused with RRF, reranked, permission-filtered in SQL."""
import re
from dataclasses import dataclass, field
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.ai.safety import neutralize, UNTRUSTED_PREAMBLE
from app.ai.textutil import keywords, overlap_score, estimate_tokens, stem
from app.core.permissions import ROLE_RANK
from app.rag.embeddings import get_embedder

RRF_K = 60


@dataclass
class Retrieved:
    chunk_id: str
    document_id: str
    title: str
    content: str
    page: int | None
    section: str | None
    vector_score: float = 0.0
    keyword_score: float = 0.0
    fused: float = 0.0
    rerank: float = 0.0
    injection_risk: float = 0.0
    file_type: str = ""


@dataclass
class RetrievalFilters:
    document_ids: list[str] | None = None
    file_types: list[str] | None = None
    tags: list[str] | None = None
    workspace_id: str | None = None


ACCESS_SQL = """
  d.org_id = :org_id AND c.org_id = :org_id AND d.deleted_at IS NULL AND d.status = 'indexed' AND c.version = d.version
  AND ( (CASE d.min_role WHEN 'viewer' THEN 10 WHEN 'member' THEN 20 WHEN 'manager' THEN 30 WHEN 'admin' THEN 40 WHEN 'owner' THEN 50 ELSE 99 END) <= :role_rank
        OR CAST(d.allowed_user_ids AS jsonb) ? :user_id )
"""


def _filters_sql(f: RetrievalFilters | None, params: dict) -> str:
    sql = ""
    if not f:
        return sql
    if f.document_ids:
        sql += " AND d.id = ANY(CAST(:doc_ids AS uuid[]))"
        params["doc_ids"] = [str(x) for x in f.document_ids]
    if f.file_types:
        sql += " AND d.file_type = ANY(:file_types)"
        params["file_types"] = f.file_types
    if f.tags:
        sql += " AND CAST(d.tags AS jsonb) ?| :tags"
        params["tags"] = f.tags
    if f.workspace_id:
        sql += " AND d.workspace_id = CAST(:ws AS uuid)"
        params["ws"] = str(f.workspace_id)
    return sql


def _vec_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def hybrid_search(db: Session, *, org_id, user_id, role: str, query: str, top_k: int = 6, candidates: int = 24,
                  filters: RetrievalFilters | None = None, mode: str = "hybrid") -> list[Retrieved]:
    if not query.strip():
        return []
    emb = get_embedder()
    base = {"org_id": str(org_id), "user_id": str(user_id), "role_rank": ROLE_RANK.get(role, 0), "lim": candidates, "model": emb.model}
    results: dict[str, Retrieved] = {}

    def add(rows, kind):
        for rank, r in enumerate(rows, start=1):
            key = str(r.id)
            item = results.get(key) or Retrieved(chunk_id=key, document_id=str(r.document_id), title=r.title, content=r.content,
                                                  page=r.page, section=r.section, injection_risk=r.injection_risk or 0, file_type=r.file_type)
            if kind == "vector":
                item.vector_score = float(r.score)
            else:
                item.keyword_score = float(r.score)
            item.fused += 1.0 / (RRF_K + rank)
            results[key] = item

    if mode in ("hybrid", "vector"):
        params = dict(base, q=_vec_literal(emb.embed([query])[0]))
        fsql = _filters_sql(filters, params)
        dim = emb.dim
        rows = db.execute(text(f"""
            SELECT c.id, c.document_id, d.title, d.file_type, c.content, c.page, c.section, c.injection_risk,
                   1 - ((c.embedding::vector({dim})) <=> CAST(:q AS vector({dim}))) AS score
            FROM document_chunks c JOIN documents d ON d.id = c.document_id
            WHERE {ACCESS_SQL} AND c.embedding_model = :model {fsql}
            ORDER BY (c.embedding::vector({dim})) <=> CAST(:q AS vector({dim})) LIMIT :lim"""), params).all()
        add(rows, "vector")
    if mode in ("hybrid", "keyword"):
        terms = [re.sub(r"[^a-z0-9]", "", w) for w in keywords(query)]
        terms = [t for t in terms if t][:12]
        if terms:
            params = dict(base, tsq=" | ".join(terms))
            fsql = _filters_sql(filters, params)
            rows = db.execute(text(f"""
                SELECT c.id, c.document_id, d.title, d.file_type, c.content, c.page, c.section, c.injection_risk,
                       ts_rank_cd(c.tsv, to_tsquery('english', :tsq)) AS score
                FROM document_chunks c JOIN documents d ON d.id = c.document_id
                WHERE {ACCESS_SQL} AND c.tsv @@ to_tsquery('english', :tsq) {fsql}
                ORDER BY score DESC LIMIT :lim"""), params).all()
            add(rows, "keyword")
    return rerank(query, list(results.values()), top_k)


def rerank(query: str, items: list[Retrieved], top_k: int) -> list[Retrieved]:
    """Lightweight reranker: fused rank + query-term coverage + phrase bonus - injection penalty.
    Pluggable: a cross-encoder or LLM reranker can replace this function without touching callers."""
    if not items:
        return []
    max_fused = max(i.fused for i in items) or 1
    qn = " ".join(stem(w) for w in keywords(query))
    for it in items:
        coverage = overlap_score(query, (it.section or "") + " " + it.content)
        cn = " ".join(stem(w) for w in keywords(it.content))
        phrase = 0.15 if len(qn) > 8 and qn in cn else 0.0
        it.rerank = round(0.45 * (it.fused / max_fused) + 0.45 * coverage + phrase + 0.1 * max(it.vector_score, 0) - 0.3 * it.injection_risk, 4)
    items.sort(key=lambda x: -x.rerank)
    return [i for i in items if i.rerank > 0.05][:top_k]


@dataclass
class AssembledContext:
    prompt_block: str
    citations: list[dict] = field(default_factory=list)
    chunks_for_demo: list[dict] = field(default_factory=list)


def assemble_context(items: list[Retrieved], max_tokens: int = 6000) -> AssembledContext:
    blocks, cites, demo, used = [], [], [], 0
    for n, it in enumerate(items, start=1):
        content = neutralize(it.content)
        t = estimate_tokens(content)
        if used + t > max_tokens:
            break
        used += t
        loc = f' page="{it.page}"' if it.page else ""
        sec = f' section="{(it.section or "")[:80]}"' if it.section else ""
        blocks.append(f'<document n="{n}" title="{it.title}"{loc}{sec}>\n{content}\n</document>')
        cites.append({"n": n, "document_id": it.document_id, "chunk_id": it.chunk_id, "title": it.title, "page": it.page,
                      "section": it.section, "snippet": it.content[:300], "score": it.rerank, "_content": it.content})
        demo.append({"n": n, "content": content})
    block = (UNTRUSTED_PREAMBLE + "\n\nRetrieved knowledge (cite as [n]):\n" + "\n\n".join(blocks)) if blocks else ""
    return AssembledContext(prompt_block=block, citations=cites, chunks_for_demo=demo)


def verify_citations(answer: str, citations: list[dict]) -> tuple[str, list[dict], dict]:
    """Keeps only citations whose marker appears in the answer and whose chunk lexically supports the cited sentence."""
    by_n = {c["n"]: c for c in citations}
    used, invalid = [], 0
    for m in re.finditer(r"\[(\d+)\]", answer):
        n = int(m.group(1))
        if n not in by_n:
            invalid += 1
            continue
        if n not in used:
            used.append(n)
    # strip markers that reference nothing
    clean = re.sub(r"\[(\d+)\]", lambda m: m.group(0) if int(m.group(1)) in by_n else "", answer)
    verified = []
    # attach markers written after the full stop ("claim. [1]") to the sentence they follow
    normalized = re.sub(r"([.!?])\s*((?:\[\d+\]\s*)+)", lambda m: " " + m.group(2).strip() + m.group(1) + " ", clean)
    sentences_ = re.split(r"(?<=[.!?])\s+|\n", normalized)
    for n in used:
        c = dict(by_n[n])
        full = c.pop("_content", c["snippet"]) + " " + (c.get("section") or "")
        claim = " ".join(s for s in sentences_ if f"[{n}]" in s)
        c["support"] = round(overlap_score(re.sub(r"\[\d+\]", "", claim), full), 2) if claim else 0.0
        c["verified"] = c["support"] >= 0.3
        verified.append(c)
    stats = {"cited": len(used), "invalid_markers": invalid, "verified": sum(1 for c in verified if c["verified"])}
    return clean, verified, stats
