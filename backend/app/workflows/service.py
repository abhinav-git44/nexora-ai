"""Workflow validation, publishing, triggering and a resumable executor (state persisted on workflow_executions.context)."""
import json
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import httpx
from croniter import croniter
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.audit import track, outcome
from app.core.crypto import encrypt_str
from app.core.plans import check_limit, increment_usage, has_feature
from app.models import (Workflow, WorkflowVersion, WorkflowExecution, WorkflowExecutionLog, Approval, Job, Membership, User, Task,
                        Record, Document, DocumentChunk, IntegrationConnection)
from app.workflows.nodes import CATALOG, handles_for, render, evaluate_condition, Pause, NodeResult, due_date_in
from app.worker.queue import handler, enqueue

MAX_NODE_RUNS = 300
TRIGGER_TYPES = {"trigger.manual": "manual", "trigger.schedule": "schedule", "trigger.webhook": "webhook", "trigger.form": "form",
                 "trigger.document_uploaded": "document_uploaded"}


# ---------------- validation ----------------
def validate_definition(defn: dict, org_features: set[str] | None = None) -> dict:
    errors, warnings = [], []
    nodes = defn.get("nodes") or []
    edges = defn.get("edges") or []
    ids = [n.get("id") for n in nodes]
    if len(ids) != len(set(ids)):
        errors.append({"message": "Duplicate node ids"})
    by_id = {n["id"]: n for n in nodes if n.get("id")}
    triggers = [n for n in nodes if str(n.get("type", "")).startswith("trigger.")]
    if len(triggers) != 1:
        errors.append({"message": f"A workflow needs exactly one trigger (found {len(triggers)})"})
    if len(nodes) > 100:
        errors.append({"message": "Workflows are limited to 100 nodes"})
    for n in nodes:
        spec = CATALOG.get(n.get("type"))
        if not spec:
            errors.append({"node_id": n.get("id"), "message": f"Unknown node type '{n.get('type')}'"})
            continue
        if spec.plan_feature and org_features is not None and spec.plan_feature not in org_features:
            errors.append({"node_id": n["id"], "message": f"'{spec.label}' requires a plan with {spec.plan_feature.replace('_', ' ')}"})
        cfg = (n.get("data") or {}).get("config") or {}
        for f in spec.fields:
            v = cfg.get(f["key"])
            if f["required"] and (v is None or str(v).strip() == ""):
                errors.append({"node_id": n["id"], "field": f["key"], "message": f"{spec.label}: '{f['label']}' is required"})
            if f["type"] == "json" and isinstance(v, str) and v.strip() and "{{" not in v:
                try:
                    json.loads(v)
                except json.JSONDecodeError:
                    errors.append({"node_id": n["id"], "field": f["key"], "message": f"{spec.label}: '{f['label']}' must be valid JSON"})
        if n["type"] == "trigger.schedule" and cfg.get("cron"):
            if not croniter.is_valid(cfg["cron"]):
                errors.append({"node_id": n["id"], "field": "cron", "message": "Invalid cron expression"})
            else:
                it = croniter(cfg["cron"], datetime.now(timezone.utc))
                a, b = it.get_next(datetime), it.get_next(datetime)
                if (b - a).total_seconds() < 300:
                    errors.append({"node_id": n["id"], "field": "cron", "message": "Schedules must be at least 5 minutes apart"})
    adj: dict[str, list[str]] = {i: [] for i in by_id}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s not in by_id or t not in by_id:
            errors.append({"message": f"Edge {e.get('id')} references a missing node"})
            continue
        if str(by_id[t].get("type", "")).startswith("trigger."):
            errors.append({"message": "Triggers cannot have incoming connections"})
        h = e.get("sourceHandle") or "out"
        if by_id[s].get("type") in CATALOG and h not in handles_for(by_id[s]) and not (h == "out" and len(handles_for(by_id[s])) == 1):
            errors.append({"node_id": s, "message": f"Invalid output handle '{h}'"})
        adj[s].append(t)
    # cycle detection
    color: dict[str, int] = {}

    def dfs(u) -> bool:
        color[u] = 1
        for v in adj.get(u, []):
            if color.get(v) == 1 or (color.get(v) is None and dfs(v)):
                return True
        color[u] = 2
        return False
    if any(color.get(i) is None and dfs(i) for i in by_id):
        errors.append({"message": "Workflow contains a cycle; use a Loop node instead"})
    if triggers:
        seen, stack = set(), [triggers[0]["id"]]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            stack.extend(adj.get(u, []))
        for i in by_id:
            if i not in seen:
                warnings.append({"node_id": i, "message": f"'{(by_id[i].get('data') or {}).get('label') or by_id[i]['type']}' is not connected to the trigger and will never run"})
        if len(nodes) == 1:
            warnings.append({"message": "Add at least one action after the trigger"})
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def org_features(db: Session, org_id) -> set[str]:
    from app.core.plans import effective_plan
    return set(effective_plan(db, org_id)["features"])


def publish(db: Session, wf: Workflow, user_id) -> WorkflowVersion:
    from app.core.errors import bad_request
    result = validate_definition(wf.draft_definition, org_features(db, wf.org_id))
    if not result["valid"]:
        raise bad_request("Workflow has validation errors", "invalid_workflow", result)
    version = (wf.published_version or 0) + 1
    v = WorkflowVersion(org_id=wf.org_id, workflow_id=wf.id, version=version, definition=wf.draft_definition, published_by=user_id)
    db.add(v)
    trig = next(n for n in wf.draft_definition["nodes"] if n["type"].startswith("trigger."))
    wf.trigger_type = TRIGGER_TYPES[trig["type"]]
    cfg = (trig.get("data") or {}).get("config") or {}
    wf.schedule_cron = cfg.get("cron") if wf.trigger_type == "schedule" else None
    wf.next_run_at = croniter(wf.schedule_cron, datetime.now(timezone.utc)).get_next(datetime) if wf.schedule_cron else None
    if wf.trigger_type in ("webhook", "form") and not wf.webhook_token:
        wf.webhook_token = secrets.token_urlsafe(24)
    if wf.trigger_type == "webhook" and not wf.webhook_secret_enc:
        wf.webhook_secret_enc = encrypt_str(secrets.token_hex(24))
    wf.published_version, wf.status = version, "published"
    track(db, "workflow_published", org_id=wf.org_id, user_id=user_id, properties={"version": version, "trigger": wf.trigger_type,
                                                                                    "nodes": len(wf.draft_definition["nodes"])})
    return v


# ---------------- triggering ----------------
def create_execution(db: Session, wf: Workflow, trigger: str, payload: dict, user_id=None, retry_of=None, attempt: int = 1) -> WorkflowExecution:
    from app.core.errors import bad_request
    if wf.status != "published" or not wf.published_version:
        raise bad_request("Workflow is not published")
    check_limit(db, wf.org_id, "workflow_runs")
    ex = WorkflowExecution(org_id=wf.org_id, workflow_id=wf.id, version=wf.published_version, trigger=trigger, input=payload or {},
                           triggered_by=user_id, retry_of=retry_of, attempt=attempt, status="queued")
    db.add(ex)
    db.flush()
    increment_usage(db, wf.org_id, "workflow_runs")
    track(db, "workflow_executed", org_id=wf.org_id, user_id=user_id, properties={"trigger": trigger, "workflow_id": str(wf.id)})
    enqueue(db, "run_workflow", {"execution_id": str(ex.id)}, org_id=wf.org_id, max_attempts=1)
    return ex


def fire_event_trigger(db: Session, org_id, event: str, payload: dict):
    wfs = db.scalars(select(Workflow).where(Workflow.org_id == org_id, Workflow.status == "published", Workflow.trigger_type == event)).all()
    for wf in wfs:
        v = db.scalar(select(WorkflowVersion).where(WorkflowVersion.workflow_id == wf.id, WorkflowVersion.version == wf.published_version))
        trig = next((n for n in v.definition["nodes"] if n["type"].startswith("trigger.")), {})
        ft = ((trig.get("data") or {}).get("config") or {}).get("file_type")
        if ft and payload.get("file_type") != ft:
            continue
        try:
            create_execution(db, wf, event, payload)
        except Exception:
            continue  # plan limit etc.: do not break indexing


def enqueue_due_scheduled(db: Session):
    now = datetime.now(timezone.utc)
    for wf in db.scalars(select(Workflow).where(Workflow.status == "published", Workflow.trigger_type == "schedule",
                                                Workflow.next_run_at <= now).with_for_update(skip_locked=True)):
        wf.next_run_at = croniter(wf.schedule_cron, now).get_next(datetime)
        try:
            create_execution(db, wf, "schedule", {"scheduled_at": now.isoformat()})
        except Exception:
            pass


# ---------------- executor ----------------
class Runner:
    def __init__(self, db: Session, ex: WorkflowExecution, defn: dict, wf: Workflow):
        self.db, self.ex, self.wf = db, ex, wf
        self.nodes = {n["id"]: n for n in defn["nodes"]}
        self.edges = defn.get("edges", [])
        self.actor_id = ex.triggered_by or wf.created_by
        m = db.scalar(select(Membership).where(Membership.org_id == wf.org_id, Membership.user_id == self.actor_id)) if self.actor_id else None
        self.role = m.role if m and m.status == "active" else "member"
        self.node_runs = 0

    def successors(self, nid: str, handle: str | None) -> list[str]:
        if handle is None:
            return []
        return [e["target"] for e in self.edges if e["source"] == nid and (e.get("sourceHandle") or "out") == handle]

    def log(self, node, status, inp, out, err, ms):
        self.db.add(WorkflowExecutionLog(org_id=self.ex.org_id, execution_id=self.ex.id, node_id=node["id"], node_type=node["type"],
                                         status=status, input=inp, output=out, error=err, duration_ms=ms))

    def run_queue(self, ctx: dict, queue: list[str], visited: set, allow_pause: bool = True):
        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            self.node_runs += 1
            if self.node_runs > MAX_NODE_RUNS:
                raise RuntimeError("Node execution limit exceeded")
            node = self.nodes[nid]
            cfg_raw = (node.get("data") or {}).get("config") or {}
            cfg = render(cfg_raw, ctx)
            t0 = time.perf_counter()
            try:
                res = self.exec_node(node, cfg, ctx, allow_pause)
            except Pause as p:
                if not allow_pause:
                    raise RuntimeError(f"'{node['type']}' cannot be used inside a loop")
                ms = int((time.perf_counter() - t0) * 1000)
                self.log(node, "waiting", cfg, p.info, None, ms)
                visited.add(nid)
                if p.kind == "delay":
                    ctx["nodes"][nid] = {"output": p.info}
                    queue[:0] = self.successors(nid, "out")
                ctx["paused"] = {"kind": p.kind, "node_id": nid, **p.info}
                raise
            except Exception as e:
                ms = int((time.perf_counter() - t0) * 1000)
                msg = str(getattr(e, "detail", None) or e)
                self.log(node, "failed", cfg, None, msg[:2000], ms)
                raise RuntimeError(f"{(node.get('data') or {}).get('label') or node['type']}: {msg}") from e
            ms = int((time.perf_counter() - t0) * 1000)
            visited.add(nid)
            ctx["nodes"][nid] = {"output": res.output}
            self.log(node, "succeeded" if res.handle is not None else "skipped", cfg, res.output, None, ms)
            queue.extend(self.successors(nid, res.handle))

    # ---- node implementations ----
    def exec_node(self, node: dict, cfg: dict, ctx: dict, allow_pause: bool) -> NodeResult:
        t = node["type"]
        db, org_id = self.db, self.ex.org_id
        if t.startswith("trigger."):
            return NodeResult(output=ctx["trigger"])
        if t == "logic.if":
            ok = evaluate_condition(cfg.get("left"), cfg.get("operator"), cfg.get("right"))
            return NodeResult(output={"result": ok}, handle="true" if ok else "false")
        if t == "logic.filter":
            ok = evaluate_condition(cfg.get("left"), cfg.get("operator"), cfg.get("right"))
            return NodeResult(output={"passed": ok}, handle="out" if ok else None)
        if t == "logic.branch":
            cases = [c.strip() for c in str((node.get("data") or {}).get("config", {}).get("cases", "")).split(",") if c.strip()]
            val = str(cfg.get("value", "")).strip()
            match = next((c for c in cases if c.lower() == val.lower()), "default")
            return NodeResult(output={"matched": match}, handle=match)
        if t == "logic.delay":
            secs = max(0, int(float(cfg.get("seconds") or 0)))
            if secs == 0:
                return NodeResult(output={"delayed_s": 0})
            raise Pause("delay", {"resume_at": (datetime.now(timezone.utc) + timedelta(seconds=secs)).isoformat(), "seconds": secs})
        if t == "logic.approval":
            ap = Approval(org_id=org_id, source_type="workflow_execution", source_id=self.ex.id, requested_by=self.actor_id,
                          title=str(cfg.get("title") or f"Approve step in {self.wf.name}")[:300],
                          details={"workflow_id": str(self.wf.id), "workflow": self.wf.name, "node_id": node["id"], "details": cfg.get("details")})
            db.add(ap)
            db.flush()
            from app.modules.notifications import notify
            for mm in db.scalars(select(Membership).where(Membership.org_id == org_id, Membership.role.in_(["manager", "admin", "owner"]),
                                                          Membership.status == "active")):
                notify(db, org_id, mm.user_id, "approval_request", f"Approval needed: {ap.title}", link="/app/approvals")
            raise Pause("approval", {"approval_id": str(ap.id)})
        if t == "logic.loop":
            items = cfg.get("items")
            if isinstance(items, str):
                try:
                    items = json.loads(items)
                except json.JSONDecodeError:
                    items = [s.strip() for s in items.split(",") if s.strip()]
            if not isinstance(items, list):
                raise ValueError("Loop items must be a list")
            items = items[: int(float(cfg.get("max_items") or 50))]
            results = []
            for i, item in enumerate(items):
                sub = {**ctx, "item": item, "index": i, "nodes": dict(ctx["nodes"])}
                visited: set = set()
                self.run_queue(sub, self.successors(node["id"], "each"), visited, allow_pause=False)
                results.append({k: v for k, v in sub["nodes"].items() if k in visited})
            ctx.setdefault("loop_visited", []).extend(sorted({k for r in results for k in r}))
            return NodeResult(output={"count": len(items), "results": results}, handle="done")
        if t == "action.send_email":
            from app.core.email import send_email
            to = str(cfg.get("to", "")).strip()
            if "@" not in to:
                raise ValueError(f"Invalid recipient '{to}'")
            row = send_email(db, to, str(cfg.get("subject"))[:200], str(cfg.get("body"))[:20000], kind="workflow")
            return NodeResult(output={"status": row.status, "to": to})
        if t == "action.ai_generate":
            from app.ai.gateway import generate
            from app.ai.providers.base import LLMRequest, ChatMessage
            from app.ai.safety import UNTRUSTED_PREAMBLE
            route = cfg.get("route") if cfg.get("route") in ("chat", "summarize", "analysis") else "chat"
            r = generate(db, LLMRequest(messages=[ChatMessage(role="user", content=str(cfg.get("prompt"))[:30000])],
                                        system="You are a business automation assistant. Respond concisely. " + UNTRUSTED_PREAMBLE, task_type=route,
                                        metadata={"demo_handler": "summarize" if route == "summarize" else None, "text": str(cfg.get("prompt"))}),
                         org_id=org_id, user_id=self.actor_id, feature="workflow")
            return NodeResult(output={"text": r.text, "model": r.model, "demo": r.demo})
        if t == "action.summarize_document":
            doc = db.get(Document, uuid.UUID(str(cfg.get("document_id"))))
            if not doc or doc.org_id != org_id or doc.deleted_at:
                raise ValueError("Document not found")
            if doc.summary:
                return NodeResult(output={"summary": doc.summary, "title": doc.title})
            chunks = db.scalars(select(DocumentChunk.content).where(DocumentChunk.document_id == doc.id, DocumentChunk.org_id == org_id)
                                .order_by(DocumentChunk.chunk_index)).all()
            from app.agents.tools import t_summarize, ToolContext
            out = t_summarize(ToolContext(db, org_id, self.actor_id, self.role, ""), {"text": "\n".join(chunks)})
            return NodeResult(output={"summary": out["summary"], "title": doc.title})
        if t == "action.extract_data":
            from app.modules.chat import schema_from_fields, FieldSpec
            from app.ai.gateway import generate
            from app.ai.providers.base import LLMRequest, ChatMessage
            from app.ai.safety import neutralize, UNTRUSTED_PREAMBLE
            fields = [FieldSpec(name=f.strip().replace(" ", "_")) for f in str(cfg.get("fields")).split(",") if f.strip()]
            text = neutralize(str(cfg.get("text"))[:30000])
            r = generate(db, LLMRequest(messages=[ChatMessage(role="user", content=f"<document>\n{text}\n</document>\nExtract the fields.")],
                                        system="Extract structured data. " + UNTRUSTED_PREAMBLE, task_type="extract",
                                        json_schema=schema_from_fields(fields), metadata={"text": text}),
                         org_id=org_id, user_id=self.actor_id, feature="workflow")
            return NodeResult(output=r.parsed or {})
        if t == "action.create_task":
            assignee = None
            if cfg.get("assignee_email"):
                u = db.scalar(select(User).where(User.email == str(cfg["assignee_email"]).lower()))
                if u and db.scalar(select(Membership).where(Membership.org_id == org_id, Membership.user_id == u.id, Membership.status == "active")):
                    assignee = u.id
            from datetime import date
            due = due_date_in(cfg.get("due_in_days"))
            task = Task(org_id=org_id, title=str(cfg.get("title"))[:300], description=str(cfg.get("description") or "")[:5000],
                        priority=cfg.get("priority") if cfg.get("priority") in ("low", "medium", "high", "urgent") else "medium",
                        assignee_id=assignee, due_date=date.fromisoformat(due) if due else None, created_by=self.actor_id, source="workflow",
                        labels=["workflow"])
            db.add(task)
            db.flush()
            if assignee:
                from app.modules.notifications import notify
                notify(db, org_id, assignee, "task_assigned", f"New task: {task.title}", f"Created by workflow {self.wf.name}", link=f"/app/tasks?task={task.id}")
            track(db, "task_created", org_id=org_id, user_id=self.actor_id, properties={"source": "workflow"})
            return NodeResult(output={"task_id": str(task.id), "title": task.title})
        if t == "action.update_record":
            data = cfg.get("data")
            if isinstance(data, str):
                data = json.loads(data or "{}")
            if not isinstance(data, dict):
                raise ValueError("Record data must be a JSON object")
            coll = str(cfg.get("collection"))[:60]
            rec = None
            if cfg.get("match_field"):
                for r in db.scalars(select(Record).where(Record.org_id == org_id, Record.collection == coll).limit(5000)):
                    if str(r.data.get(cfg["match_field"])) == str(cfg.get("match_value")):
                        rec = r
                        break
            if rec:
                rec.data = {**rec.data, **data}
                action = "updated"
            else:
                rec = Record(org_id=org_id, collection=coll, data=data)
                db.add(rec)
                action = "created"
            db.flush()
            return NodeResult(output={"record_id": str(rec.id), "action": action})
        if t == "action.send_webhook":
            from app.core.netguard import assert_public_url
            body = cfg.get("body")
            if isinstance(body, str):
                body = json.loads(body) if body.strip() else {}
            r = httpx.post(assert_public_url(str(cfg.get("url"))), json=body, timeout=15)
            if r.status_code >= 400:
                raise RuntimeError(f"Webhook returned HTTP {r.status_code}")
            return NodeResult(output={"status_code": r.status_code, "response": r.text[:1000]})
        if t == "action.n8n":
            conn = db.scalar(select(IntegrationConnection).where(IntegrationConnection.org_id == org_id, IntegrationConnection.provider == "n8n",
                                                                 IntegrationConnection.status == "connected"))
            if not conn:
                raise RuntimeError("n8n is not connected. Connect it in Integrations.")
            from app.integrations.providers import n8n_call_webhook
            body = cfg.get("body")
            if isinstance(body, str):
                body = json.loads(body) if body.strip() else {}
            return NodeResult(output=n8n_call_webhook(conn, str(cfg.get("webhook_path")), body or {}))
        if t == "action.generate_report":
            from app.ai.gateway import generate
            from app.ai.providers.base import LLMRequest, ChatMessage
            from app.ai.safety import neutralize, UNTRUSTED_PREAMBLE
            src = neutralize(str(cfg.get("source") or "")[:30000])
            r = generate(db, LLMRequest(messages=[ChatMessage(role="user", content=f"<document>\n{src}\n</document>\n\nWrite a business report on: {cfg.get('topic')}. "
                                                              "Sections: Executive summary, Findings, Recommendations.")],
                                        system="You write accurate business reports from provided material only. " + UNTRUSTED_PREAMBLE,
                                        task_type="analysis", metadata={"demo_handler": "report", "text": src or str(cfg.get("topic"))}),
                         org_id=org_id, user_id=self.actor_id, feature="workflow")
            from app.modules.knowledge import create_document
            fake_ctx = SimpleNamespace(org_id=org_id, user=SimpleNamespace(id=self.actor_id), ip=None)
            name = f"Report - {str(cfg.get('topic'))[:60]} - {datetime.now(timezone.utc):%Y%m%d-%H%M%S}.md"
            try:
                doc = create_document(db, fake_ctx, name, r.text.encode(), tags=["report", "workflow"])
                doc_id = str(doc.id)
            except Exception:
                doc_id = None
            return NodeResult(output={"report": r.text, "document_id": doc_id})
        raise ValueError(f"Unsupported node type {t}")


def execute(db: Session, ex: WorkflowExecution):
    wf = db.get(Workflow, ex.workflow_id)
    v = db.scalar(select(WorkflowVersion).where(WorkflowVersion.workflow_id == wf.id, WorkflowVersion.version == ex.version))
    runner = Runner(db, ex, v.definition, wf)
    ctx = dict(ex.context or {})
    if not ctx:
        trig = next(n for n in v.definition["nodes"] if n["type"].startswith("trigger."))
        ctx = {"trigger": ex.input or {}, "nodes": {}, "queue": [trig["id"]], "visited": [],
               "workflow": {"id": str(wf.id), "name": wf.name}, "execution": {"id": str(ex.id)}}
        ex.started_at = datetime.now(timezone.utc)
    ctx.pop("paused", None)
    queue, visited = list(ctx.get("queue", [])), set(ctx.get("visited", []))
    ex.status = "running"
    db.flush()
    try:
        runner.run_queue(ctx, queue, visited)
        ex.status = "succeeded"
        ex.output = {k: v["output"] for k, v in ctx["nodes"].items()}
    except Pause as p:
        ex.status = "waiting_approval" if p.kind == "approval" else "waiting"
        if p.kind == "delay":
            enqueue(db, "run_workflow", {"execution_id": str(ex.id)}, org_id=ex.org_id, delay_s=int(p.info["seconds"]), max_attempts=1)
    except Exception as e:
        ex.status, ex.error = "failed", str(e)[:2000]
    ctx["queue"], ctx["visited"] = queue, sorted(visited)
    ex.context = json.loads(json.dumps(ctx, default=str))
    if ex.status in ("succeeded", "failed"):
        ex.finished_at = datetime.now(timezone.utc)
        ex.duration_ms = int((ex.finished_at - ex.started_at).total_seconds() * 1000) if ex.started_at else None
        track(db, "workflow_completed" if ex.status == "succeeded" else "workflow_failed", org_id=ex.org_id, user_id=ex.triggered_by,
              properties={"workflow_id": str(wf.id), "duration_ms": ex.duration_ms, "trigger": ex.trigger})
        if ex.status == "succeeded":
            outcome(db, "workflow_completed", org_id=ex.org_id, user_id=ex.triggered_by, properties={"workflow_id": str(wf.id)})
        else:
            from app.modules.notifications import notify
            notify(db, ex.org_id, wf.created_by, "workflow_alert", f"Workflow failed: {wf.name}", ex.error, link=f"/app/workflows/{wf.id}?execution={ex.id}")
    return ex


@handler("run_workflow")
def handle_run_workflow(db: Session, job: Job):
    ex = db.get(WorkflowExecution, uuid.UUID(job.payload["execution_id"]))
    if not ex or ex.org_id != job.org_id or ex.status in ("succeeded", "failed", "cancelled", "waiting_approval"):
        return
    execute(db, ex)


def resume_after_approval(db: Session, ap: Approval, decision: str):
    ex = db.get(WorkflowExecution, ap.source_id)
    if not ex or ex.status != "waiting_approval":
        return
    ctx = dict(ex.context)
    paused = ctx.get("paused") or {}
    nid = paused.get("node_id")
    wf = db.get(Workflow, ex.workflow_id)
    v = db.scalar(select(WorkflowVersion).where(WorkflowVersion.workflow_id == wf.id, WorkflowVersion.version == ex.version))
    handle = "approved" if decision == "approved" else "rejected"
    ctx["nodes"][nid] = {"output": {"decision": decision, "approval_id": str(ap.id)}}
    succ = [e["target"] for e in v.definition.get("edges", []) if e["source"] == nid and (e.get("sourceHandle") or "out") == handle]
    ctx["queue"] = succ + list(ctx.get("queue", []))
    ctx.pop("paused", None)
    ex.context, ex.status = ctx, "queued"
    db.add(WorkflowExecutionLog(org_id=ex.org_id, execution_id=ex.id, node_id=nid, node_type="logic.approval", status="succeeded",
                                output={"decision": decision}))
    enqueue(db, "run_workflow", {"execution_id": str(ex.id)}, org_id=ex.org_id, max_attempts=1)
