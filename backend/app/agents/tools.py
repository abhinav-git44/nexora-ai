"""Agent tool registry. Every tool declares: JSON schema, minimum role, and whether it is sensitive (side effects outside
NEXORA). Sensitive tools ALWAYS require human approval regardless of agent configuration."""
import ast
import json
import operator
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Callable
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.permissions import role_at_least


@dataclass
class ToolContext:
    db: Session
    org_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    org_name: str
    source: str = "agent"


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    min_role: str
    sensitive: bool
    fn: Callable[[ToolContext, dict], dict]
    category: str = "general"


def obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required if required is not None else list(props), "additionalProperties": False}


# ---------------- implementations ----------------
def t_search_knowledge(tc: ToolContext, a: dict) -> dict:
    from app.rag.retrieval import hybrid_search
    items = hybrid_search(tc.db, org_id=tc.org_id, user_id=tc.user_id, role=tc.role, query=a["query"], top_k=min(int(a.get("top_k") or 5), 8))
    return {"results": [{"title": i.title, "page": i.page, "section": i.section, "content": i.content[:1200], "document_id": i.document_id,
                         "score": i.rerank} for i in items]}


def t_create_task(tc: ToolContext, a: dict) -> dict:
    from app.models import Task
    due = None
    if a.get("due_date"):
        try:
            due = date.fromisoformat(a["due_date"])
        except ValueError:
            due = None
    pr = a.get("priority") if a.get("priority") in ("low", "medium", "high", "urgent") else "medium"
    t = Task(org_id=tc.org_id, title=a["title"][:300], description=a.get("description", "")[:5000], priority=pr, due_date=due,
             created_by=tc.user_id, source=tc.source, labels=["ai-generated"])
    tc.db.add(t)
    tc.db.flush()
    from app.core.audit import track
    track(tc.db, "task_created", org_id=tc.org_id, user_id=tc.user_id, properties={"source": tc.source})
    return {"task_id": str(t.id), "title": t.title, "priority": t.priority, "due_date": a.get("due_date")}


def t_list_tasks(tc: ToolContext, a: dict) -> dict:
    from app.models import Task
    q = select(Task).where(Task.org_id == tc.org_id)
    if a.get("status") and a["status"] != "any":
        q = q.where(Task.status == a["status"])
    rows = tc.db.scalars(q.order_by(Task.created_at.desc()).limit(50)).all()
    return {"tasks": [{"title": t.title, "status": t.status, "priority": t.priority, "due_date": t.due_date.isoformat() if t.due_date else None}
                      for t in rows]}


def t_query_dataset(tc: ToolContext, a: dict) -> dict:
    from app.data.service import run_nl_query, find_dataset
    ds = find_dataset(tc.db, tc.org_id, a.get("dataset") or "")
    if not ds:
        from app.models import Dataset
        names = tc.db.scalars(select(Dataset.name).where(Dataset.org_id == tc.org_id)).all()
        return {"error": "dataset not found", "available_datasets": names}
    res = run_nl_query(tc.db, tc.org_id, tc.user_id, ds, a["question"], feature="agent")
    return {"sql": res["sql"], "columns": res["columns"], "rows": res["rows"][:50], "row_count": res["row_count"]}


def t_summarize(tc: ToolContext, a: dict) -> dict:
    from app.ai.gateway import generate
    from app.ai.providers.base import LLMRequest, ChatMessage
    from app.ai.safety import UNTRUSTED_PREAMBLE, neutralize
    text = neutralize(a["text"][:40000])
    r = generate(tc.db, LLMRequest(messages=[ChatMessage(role="user", content=f"<document>\n{text}\n</document>\nSummarise in bullets.")],
                                   system="Summarise faithfully. " + UNTRUSTED_PREAMBLE, task_type="summarize",
                                   metadata={"demo_handler": "summarize", "text": text}), org_id=tc.org_id, user_id=tc.user_id, feature="agent")
    return {"summary": r.text}


def t_extract_action_items(tc: ToolContext, a: dict) -> dict:
    from app.modules.chat import extract_tasks_ai
    tasks, _ = extract_tasks_ai(tc.db, tc.org_id, tc.user_id, a["text"], feature="agent")
    return {"action_items": tasks}


_ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow,
        ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos}


def safe_eval(expr: str) -> float:
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _ops:
            if isinstance(n.op, ast.Pow) and abs(ev(n.right)) > 10:
                raise ValueError("exponent too large")
            return _ops[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _ops:
            return _ops[type(n.op)](ev(n.operand))
        raise ValueError("unsupported expression")
    if len(expr) > 200:
        raise ValueError("expression too long")
    return ev(ast.parse(expr, mode="eval"))


def t_calculate(tc: ToolContext, a: dict) -> dict:
    return {"expression": a["expression"], "result": safe_eval(a["expression"])}


def t_search_records(tc: ToolContext, a: dict) -> dict:
    from app.models import Record
    rows = tc.db.scalars(select(Record).where(Record.org_id == tc.org_id, Record.collection == a["collection"]).limit(200)).all()
    q = (a.get("query") or "").lower()
    hits = [r for r in rows if not q or q in json.dumps(r.data).lower()][:25]
    return {"records": [{"id": str(r.id), **r.data} for r in hits], "total": len(hits)}


def t_create_record(tc: ToolContext, a: dict) -> dict:
    from app.models import Record
    try:
        data = json.loads(a["data_json"]) if isinstance(a.get("data_json"), str) else {}
    except json.JSONDecodeError:
        raise ValueError("data_json must be a JSON object")
    if not isinstance(data, dict) or len(json.dumps(data)) > 20000:
        raise ValueError("data_json must be a JSON object under 20KB")
    r = Record(org_id=tc.org_id, collection=a["collection"][:60], data=data)
    tc.db.add(r)
    tc.db.flush()
    return {"record_id": str(r.id), "collection": r.collection}


def t_fetch_url(tc: ToolContext, a: dict) -> dict:
    from app.core.netguard import assert_public_url
    import re
    url = assert_public_url(a["url"])
    with httpx.Client(timeout=10, follow_redirects=False) as c:
        r = c.get(url, headers={"User-Agent": "NEXORA-AI-Agent/1.0"})
    body = r.text[:200_000]
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", body, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return {"status": r.status_code, "url": url, "content": text[:6000]}


def t_send_email(tc: ToolContext, a: dict) -> dict:
    from app.core.email import send_email
    row = send_email(tc.db, a["to"], a["subject"][:200], a["body"][:10000], kind="agent_email")
    return {"status": row.status, "to": a["to"]}


def t_send_webhook(tc: ToolContext, a: dict) -> dict:
    from app.core.netguard import assert_public_url
    url = assert_public_url(a["url"])
    try:
        payload = json.loads(a.get("payload_json") or "{}")
    except json.JSONDecodeError:
        payload = {"text": a.get("payload_json")}
    r = httpx.post(url, json=payload, timeout=10)
    return {"status_code": r.status_code, "response": r.text[:500]}


REGISTRY: dict[str, Tool] = {t.name: t for t in [
    Tool("search_knowledge", "Search the organisation's knowledge base (permission-aware). Returns relevant passages with titles and pages.",
         obj({"query": {"type": "string"}, "top_k": {"type": "integer"}}, ["query", "top_k"]), "viewer", False, t_search_knowledge, "knowledge"),
    Tool("create_task", "Create a task in NEXORA task management.",
         obj({"title": {"type": "string"}, "description": {"type": "string"}, "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
              "due_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"}}), "member", False, t_create_task, "tasks"),
    Tool("list_tasks", "List recent tasks, optionally filtered by status.",
         obj({"status": {"type": "string", "enum": ["any", "todo", "in_progress", "in_review", "done"]}}), "viewer", False, t_list_tasks, "tasks"),
    Tool("query_dataset", "Answer a quantitative question over an uploaded dataset using validated read-only SQL.",
         obj({"dataset": {"type": "string", "description": "dataset name"}, "question": {"type": "string"}}), "viewer", False, t_query_dataset, "data"),
    Tool("summarize_text", "Summarise a block of text.", obj({"text": {"type": "string"}}), "viewer", False, t_summarize, "ai"),
    Tool("extract_action_items", "Extract action items (title, owner, due date, priority) from notes or conversations.",
         obj({"text": {"type": "string"}}), "viewer", False, t_extract_action_items, "ai"),
    Tool("calculate", "Evaluate an arithmetic expression (+ - * / % **).", obj({"expression": {"type": "string"}}), "viewer", False, t_calculate, "utility"),
    Tool("search_records", "Search business records in a collection (e.g. leads, candidates, tickets).",
         obj({"collection": {"type": "string"}, "query": {"type": "string"}}), "viewer", False, t_search_records, "records"),
    Tool("create_record", "Create a business record in a collection. data_json is a JSON object string.",
         obj({"collection": {"type": "string"}, "data_json": {"type": "string"}}), "member", False, t_create_record, "records"),
    Tool("fetch_url", "Fetch a public web page and return its text (read-only, public internet only).",
         obj({"url": {"type": "string"}}), "member", False, t_fetch_url, "web"),
    Tool("send_email", "Send an email on behalf of the organisation. ALWAYS requires human approval.",
         obj({"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}), "member", True, t_send_email, "communication"),
    Tool("send_webhook", "POST a JSON payload to an external URL. ALWAYS requires human approval.",
         obj({"url": {"type": "string"}, "payload_json": {"type": "string"}}), "manager", True, t_send_webhook, "communication"),
]}


def tool_catalog() -> list[dict]:
    return [{"name": t.name, "description": t.description, "parameters": t.parameters, "min_role": t.min_role, "sensitive": t.sensitive,
             "category": t.category} for t in REGISTRY.values()]


def check_tool_permission(tool: Tool, role: str) -> bool:
    return role_at_least(role, tool.min_role)
