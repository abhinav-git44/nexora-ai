"""Workflow node catalogue and executors. Node config values support {{path.to.value}} templating against the run context."""
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

TEMPLATE = re.compile(r"\{\{\s*([a-zA-Z0-9_.\-]+)\s*\}\}")


def lookup(ctx: dict, path: str):
    cur: Any = ctx
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
    return cur


def render(value, ctx: dict):
    if isinstance(value, str):
        m = TEMPLATE.fullmatch(value.strip())
        if m:  # whole-value template keeps the original type
            v = lookup(ctx, m.group(1))
            return v if v is not None else ""
        return TEMPLATE.sub(lambda mm: _s(lookup(ctx, mm.group(1))), value)
    if isinstance(value, dict):
        return {k: render(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, ctx) for v in value]
    return value


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str)
    return str(v)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def evaluate_condition(left, op: str, right) -> bool:
    ls, rs = _s(left).strip(), _s(right).strip()
    ln, rn = _num(left), _num(right)
    return {
        "equals": lambda: ls.lower() == rs.lower(),
        "not_equals": lambda: ls.lower() != rs.lower(),
        "contains": lambda: rs.lower() in ls.lower(),
        "not_contains": lambda: rs.lower() not in ls.lower(),
        "greater_than": lambda: ln is not None and rn is not None and ln > rn,
        "less_than": lambda: ln is not None and rn is not None and ln < rn,
        "is_empty": lambda: ls == "" or ls in ("[]", "{}"),
        "is_not_empty": lambda: not (ls == "" or ls in ("[]", "{}")),
    }.get(op, lambda: False)()


OPERATORS = ["equals", "not_equals", "contains", "not_contains", "greater_than", "less_than", "is_empty", "is_not_empty"]


@dataclass
class NodeSpec:
    type: str
    category: str  # trigger | action | logic
    label: str
    description: str
    fields: list[dict]  # [{key, label, type, required, options?, placeholder?}]
    handles: list[str]  # output handles; ["out"] default
    plan_feature: str | None = None


def F(key, label, type_="text", required=False, **kw):
    return {"key": key, "label": label, "type": type_, "required": required, **kw}


CATALOG: dict[str, NodeSpec] = {s.type: s for s in [
    NodeSpec("trigger.manual", "trigger", "Manual trigger", "Run on demand from the workflow page or API.",
             [F("input_example", "Example input (JSON)", "json")], ["out"]),
    NodeSpec("trigger.schedule", "trigger", "Schedule", "Run on a cron schedule (UTC).",
             [F("cron", "Cron expression", required=True, placeholder="0 9 * * 1-5")], ["out"]),
    NodeSpec("trigger.webhook", "trigger", "Webhook", "Run when an external system POSTs JSON to the workflow URL (HMAC-signed).",
             [F("require_signature", "Require HMAC signature", "boolean")], ["out"]),
    NodeSpec("trigger.form", "trigger", "Form submission", "Run when someone submits the workflow's hosted form.",
             [F("title", "Form title", required=True), F("fields", "Fields (comma separated)", required=True, placeholder="name, email, message")], ["out"]),
    NodeSpec("trigger.document_uploaded", "trigger", "New document uploaded", "Run when a document finishes indexing in the knowledge base.",
             [F("file_type", "Only file type (optional)", "select", options=["", "pdf", "docx", "txt", "csv", "xlsx", "md"])], ["out"]),
    NodeSpec("action.send_email", "action", "Send email", "Send an email (templated).",
             [F("to", "To", required=True), F("subject", "Subject", required=True), F("body", "Body", "textarea", required=True)], ["out"]),
    NodeSpec("action.ai_generate", "action", "Generate AI response", "Generate text with the AI gateway.",
             [F("prompt", "Prompt", "textarea", required=True), F("route", "Model route", "select", options=["chat", "summarize", "analysis"])], ["out"]),
    NodeSpec("action.summarize_document", "action", "Summarise document", "Summarise a knowledge-base document.",
             [F("document_id", "Document ID", required=True, placeholder="{{trigger.document_id}}")], ["out"]),
    NodeSpec("action.extract_data", "action", "Extract structured data", "Extract named fields from text.",
             [F("text", "Text", "textarea", required=True), F("fields", "Fields (comma separated)", required=True)], ["out"]),
    NodeSpec("action.create_task", "action", "Create task", "Create a task in task management.",
             [F("title", "Title", required=True), F("description", "Description", "textarea"),
              F("priority", "Priority", "select", options=["low", "medium", "high", "urgent"]), F("assignee_email", "Assignee email"),
              F("due_in_days", "Due in days", "number")], ["out"]),
    NodeSpec("action.update_record", "action", "Create / update record", "Upsert a business record by a match field.",
             [F("collection", "Collection", required=True), F("match_field", "Match field"), F("match_value", "Match value"),
              F("data", "Data (JSON)", "json", required=True)], ["out"]),
    NodeSpec("action.send_webhook", "action", "Send webhook", "POST JSON to an external URL (public internet only).",
             [F("url", "URL", required=True), F("body", "Body (JSON)", "json")], ["out"], plan_feature="workflows_advanced"),
    NodeSpec("action.n8n", "action", "Run n8n workflow", "Call an n8n webhook through the connected n8n integration.",
             [F("webhook_path", "n8n webhook path", required=True, placeholder="lead-enrichment"), F("body", "Body (JSON)", "json")], ["out"],
             plan_feature="workflows_advanced"),
    NodeSpec("action.generate_report", "action", "Generate report", "Generate a structured business report and save it as a document.",
             [F("topic", "Topic", required=True), F("source", "Source text", "textarea")], ["out"]),
    NodeSpec("logic.if", "logic", "If / else", "Branch on a condition.",
             [F("left", "Value", required=True), F("operator", "Operator", "select", required=True, options=OPERATORS), F("right", "Compare to")],
             ["true", "false"]),
    NodeSpec("logic.filter", "logic", "Filter", "Stop this branch unless the condition is met.",
             [F("left", "Value", required=True), F("operator", "Operator", "select", required=True, options=OPERATORS), F("right", "Compare to")], ["out"]),
    NodeSpec("logic.branch", "logic", "Branch (switch)", "Route by value; handles are the case values plus 'default'.",
             [F("value", "Value", required=True), F("cases", "Cases (comma separated)", required=True)], ["default"]),
    NodeSpec("logic.delay", "logic", "Delay", "Pause the run before continuing.",
             [F("seconds", "Seconds", "number", required=True)], ["out"]),
    NodeSpec("logic.loop", "logic", "Loop", "Run the 'each' branch once per item in a list, then continue on 'done'.",
             [F("items", "Items (list)", required=True, placeholder="{{nodes.extract.output.items}}"), F("max_items", "Max items", "number")],
             ["each", "done"]),
    NodeSpec("logic.approval", "logic", "Approval", "Pause until a manager approves or rejects.",
             [F("title", "Approval title", required=True), F("details", "Details", "textarea")], ["approved", "rejected"]),
]}


def node_catalog() -> list[dict]:
    return [{"type": s.type, "category": s.category, "label": s.label, "description": s.description, "fields": s.fields,
             "handles": s.handles, "plan_feature": s.plan_feature} for s in CATALOG.values()]


def handles_for(node: dict) -> list[str]:
    spec = CATALOG[node["type"]]
    if node["type"] == "logic.branch":
        cases = [c.strip() for c in str(node.get("data", {}).get("config", {}).get("cases", "")).split(",") if c.strip()]
        return cases + ["default"]
    return spec.handles


class Pause(Exception):
    """Raised by delay/approval nodes to suspend the execution."""
    def __init__(self, kind: str, info: dict):
        self.kind, self.info = kind, info


@dataclass
class NodeResult:
    output: dict
    handle: str | None = "out"  # which outgoing handle to follow; None = stop branch


NodeFn = Callable[..., NodeResult]


def due_date_in(days) -> str | None:
    n = _num(days)
    if n is None:
        return None
    from datetime import timedelta
    return (date.today() + timedelta(days=int(n))).isoformat()
