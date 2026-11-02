"""Starter workflow templates."""


def n(id_, type_, x, y, label, **config):
    return {"id": id_, "type": type_, "position": {"x": x, "y": y}, "data": {"label": label, "config": config}}


def e(s, t, h=None):
    return {"id": f"{s}-{t}-{h or 'out'}", "source": s, "target": t, "sourceHandle": h}


WORKFLOW_TEMPLATES = {
    "doc_summary_alert": {"name": "Summarise new documents and create review tasks",
        "description": "When a document is indexed, summarise it and create a review task for PDFs.",
        "definition": {"nodes": [n("trigger", "trigger.document_uploaded", 60, 180, "Document uploaded"),
                                 n("summary", "action.summarize_document", 320, 180, "Summarise", document_id="{{trigger.document_id}}"),
                                 n("is_pdf", "logic.if", 580, 180, "Is PDF?", left="{{trigger.file_type}}", operator="equals", right="pdf"),
                                 n("task", "action.create_task", 840, 100, "Create review task", title="Review: {{trigger.title}}",
                                   description="{{nodes.summary.output.summary}}", priority="medium", due_in_days="3")],
                       "edges": [e("trigger", "summary"), e("summary", "is_pdf"), e("is_pdf", "task", "true")]}},
    "lead_intake": {"name": "Lead intake form → CRM record → follow-up",
        "description": "Capture leads from a hosted form, store them as records, qualify by budget and create a follow-up task.",
        "definition": {"nodes": [n("trigger", "trigger.form", 60, 200, "Lead form", title="Talk to sales", fields="name, email, company, budget, message"),
                                 n("record", "action.update_record", 320, 200, "Upsert lead", collection="leads", match_field="email",
                                   match_value="{{trigger.email}}", data='{"name": "{{trigger.name}}", "email": "{{trigger.email}}", "company": "{{trigger.company}}", "budget": "{{trigger.budget}}"}'),
                                 n("qualify", "logic.if", 580, 200, "Budget ≥ 5000?", left="{{trigger.budget}}", operator="greater_than", right="5000"),
                                 n("hot", "action.create_task", 840, 120, "Call within 24h", title="Call {{trigger.name}} ({{trigger.company}})",
                                   description="{{trigger.message}}", priority="high", due_in_days="1"),
                                 n("nurture", "action.send_email", 840, 300, "Nurture email", to="{{trigger.email}}", subject="Thanks for reaching out",
                                   body="Hi {{trigger.name}},\n\nThanks for contacting us. Here are some resources to get started.")],
                       "edges": [e("trigger", "record"), e("record", "qualify"), e("qualify", "hot", "true"), e("qualify", "nurture", "false")]}},
    "meeting_notes_to_tasks": {"name": "Meeting notes → AI action items → approval → tasks",
        "description": "Paste meeting notes via webhook or manual run; AI extracts action items, a manager approves, tasks are created per item.",
        "definition": {"nodes": [n("trigger", "trigger.manual", 60, 200, "Manual run", input_example='{"notes": "Priya to send the proposal by Friday."}'),
                                 n("extract", "action.ai_generate", 320, 200, "Summarise notes", prompt="Summarise these meeting notes:\n{{trigger.notes}}", route="summarize"),
                                 n("approve", "logic.approval", 580, 200, "Manager approval", title="Create tasks from meeting notes?",
                                   details="{{nodes.extract.output.text}}"),
                                 n("task", "action.create_task", 840, 200, "Create follow-up task", title="Follow up on meeting",
                                   description="{{nodes.extract.output.text}}", priority="medium", due_in_days="2")],
                       "edges": [e("trigger", "extract"), e("extract", "approve"), e("approve", "task", "approved")]}},
    "weekly_report": {"name": "Weekly AI operations report",
        "description": "Every Monday 09:00 UTC generate an operations report and email it to the team lead.",
        "definition": {"nodes": [n("trigger", "trigger.schedule", 60, 200, "Every Monday", cron="0 9 * * 1"),
                                 n("report", "action.generate_report", 320, 200, "Generate report", topic="Weekly operations summary",
                                   source="Summarise open risks, completed work and next priorities."),
                                 n("email", "action.send_email", 580, 200, "Email lead", to="ops-lead@example.com", subject="Weekly operations report",
                                   body="{{nodes.report.output.report}}")],
                       "edges": [e("trigger", "report"), e("report", "email")]}},
}
