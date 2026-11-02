"""Generates the prioritised product backlog (Jira-importable CSV) with RICE and ICE scores.
Reach = orgs/quarter affected (assumption), Impact 0.25-3, Confidence 0-1, Effort = person-weeks."""
import csv
from pathlib import Path

# epic, summary, moscow, reach, impact, confidence, effort, ease(1-10), status, sprint, acceptance
B = [
 ("Auth & Orgs", "Email/password signup with password policy", "Must", 1000, 3, 1.0, 1, 9, "Done", "S1", "Weak passwords rejected; account + org + trial created"),
 ("Auth & Orgs", "Rotating refresh tokens & session revoke", "Must", 1000, 2, 0.9, 1, 8, "Done", "S1", "Replayed refresh token fails; revoked session kills access token"),
 ("Auth & Orgs", "Role-based access control (5 roles + super admin)", "Must", 1000, 3, 1.0, 2, 7, "Done", "S1", "Viewer cannot write; admin cannot modify owner"),
 ("Auth & Orgs", "Invitations with role ceiling & expiry", "Must", 600, 2, 0.9, 1, 8, "Done", "S1", "Invite expires 7d; cannot invite above own role"),
 ("Auth & Orgs", "Email verification & password reset", "Must", 1000, 1, 1.0, 1, 9, "Done", "S1", "Single-use tokens; no account enumeration"),
 ("Auth & Orgs", "Data export & account deletion (DPDP/GDPR)", "Must", 200, 1, 0.9, 1, 7, "Done", "S5", "Export JSON; delete anonymises; sole owner blocked"),
 ("Auth & Orgs", "Google sign-in", "Should", 500, 1, 0.7, 1, 7, "Done (needs creds)", "S5", "OIDC with state cookie"),
 ("Auth & Orgs", "SAML SSO for Enterprise", "Could", 30, 2, 0.6, 4, 3, "Backlog", "V2", "IdP-initiated + SP-initiated login"),
 ("Knowledge/RAG", "Multi-format upload with validation", "Must", 900, 3, 1.0, 2, 7, "Done", "S2", "PDF/DOCX/TXT/CSV/XLSX/MD; zip-bomb & macro rejection"),
 ("Knowledge/RAG", "Hybrid retrieval (pgvector + FTS + RRF + rerank)", "Must", 900, 3, 0.9, 3, 5, "Done", "S2", "Hit@6 ≥ 95% on golden set"),
 ("Knowledge/RAG", "Citations with verification", "Must", 900, 3, 0.9, 1, 7, "Done", "S2", "Unverified citation flagged in UI"),
 ("Knowledge/RAG", "Role-aware retrieval filter in SQL", "Must", 900, 3, 1.0, 1, 8, "Done", "S2", "Member never retrieves manager-only doc"),
 ("Knowledge/RAG", "Prompt-injection detection & neutralisation", "Must", 900, 2, 0.8, 1, 7, "Done", "S2", "Flagged chunks penalised; text defanged"),
 ("Knowledge/RAG", "Versioning & re-index with strategy switch", "Should", 400, 1, 0.9, 1, 7, "Done", "S3", "Only latest version searchable"),
 ("Knowledge/RAG", "Retrieval playground with stage scores", "Should", 300, 1, 0.8, 0.5, 9, "Done", "S3", "Shows vector/keyword/fused/rerank"),
 ("Knowledge/RAG", "OCR for scanned PDFs (tesseract)", "Could", 200, 1, 0.7, 1, 6, "Adapter done", "V1", "Scanned pages extracted when engine installed"),
 ("Knowledge/RAG", "Google Drive folder sync", "Should", 600, 2, 0.6, 3, 4, "Backlog", "V1", "Incremental sync honouring Drive permissions"),
 ("Knowledge/RAG", "Cross-encoder reranker option", "Could", 900, 1, 0.5, 2, 5, "Backlog", "V1", "Measured MRR uplift on eval before rollout"),
 ("Assistant", "Multi-conversation chat with history", "Must", 1000, 3, 1.0, 2, 7, "Done", "S2", "History truncated to token budget"),
 ("Assistant", "Model gateway: routing, fallback, cost ledger", "Must", 1000, 3, 0.9, 2, 6, "Done", "S2", "Fallback on retryable errors; every call metered"),
 ("Assistant", "Summarise / extract / report modes", "Must", 700, 2, 0.9, 1, 8, "Done", "S3", "Schema-valid JSON for extraction"),
 ("Assistant", "Chat file attachments scoped retrieval", "Should", 500, 1, 0.8, 1, 7, "Done", "S3", "Answers limited to attached docs"),
 ("Assistant", "Share conversations read-only", "Should", 300, 1, 0.8, 0.5, 8, "Done", "S4", "Shared viewer cannot post"),
 ("Assistant", "Streaming responses (SSE)", "Should", 1000, 1, 0.8, 1, 6, "Backlog", "V1", "First token < 1.5s with real LLM"),
 ("Assistant", "Bring-your-own-key per workspace", "Should", 150, 1, 0.7, 1, 6, "Partially (connect+test)", "V1", "Workspace key used by gateway"),
 ("Agents", "Agent config + 8 templates", "Must", 600, 2, 0.9, 2, 7, "Done", "S3", "Template creates working agent"),
 ("Agents", "Persisted multi-step tool runtime", "Must", 600, 3, 0.8, 3, 5, "Done", "S3", "Survives worker restart; step logs"),
 ("Agents", "Human approval for sensitive tools", "Must", 600, 3, 0.9, 1, 7, "Done", "S3", "Email/webhook never run without approval"),
 ("Agents", "Agent performance metrics", "Should", 400, 1, 0.9, 0.5, 8, "Done", "S4", "Success rate, cost, tool errors"),
 ("Agents", "Scheduled agent runs", "Could", 300, 1, 0.6, 1, 6, "Backlog", "V1", "Cron trigger runs agent"),
 ("Workflows", "Visual builder (React Flow) + 20 nodes", "Must", 700, 3, 0.8, 4, 4, "Done", "S4", "Drag, connect, configure, validate"),
 ("Workflows", "Validation & versioned publish", "Must", 700, 2, 0.9, 1, 7, "Done", "S4", "Cycles/required fields blocked"),
 ("Workflows", "Approval, delay, loop, branch nodes", "Must", 700, 2, 0.8, 2, 6, "Done", "S4", "Resumable executions"),
 ("Workflows", "Webhook (HMAC) & hosted form triggers", "Must", 500, 2, 0.9, 1, 7, "Done", "S4", "Invalid signature → 401"),
 ("Workflows", "Execution logs, retry, analytics", "Must", 700, 2, 0.9, 1, 7, "Done", "S4", "Per-node input/output; retry links attempts"),
 ("Workflows", "n8n node", "Should", 200, 1, 0.7, 1, 7, "Done (needs n8n)", "S5", "Calls n8n webhook via encrypted connection"),
 ("Workflows", "AI-suggested workflows from usage", "Could", 700, 2, 0.4, 3, 3, "Backlog (flagged)", "V2", "Experiment E6"),
 ("Data", "Dataset ingest + profiling + quality checks", "Must", 400, 2, 0.9, 2, 6, "Done", "S5", "Types/roles/issues detected"),
 ("Data", "NL→SQL with AST guard & read-only exec", "Must", 400, 3, 0.8, 2, 5, "Done", "S5", "20 destructive patterns rejected"),
 ("Data", "Charts, exports, reports", "Must", 400, 2, 0.9, 1, 7, "Done", "S5", "CSV injection escaped"),
 ("Data", "Power BI analytics views + read-only role", "Should", 100, 1, 0.8, 0.5, 8, "Done", "S6", "BI connects with SELECT-only role"),
 ("Data", "Multi-table datasets & joins", "Could", 200, 2, 0.5, 3, 3, "Backlog", "V2", "Guard supports allow-listed joins"),
 ("Tasks", "Kanban/list/calendar with comments & attachments", "Must", 800, 2, 1.0, 2, 7, "Done", "S5", "Drag between columns updates status"),
 ("Tasks", "AI notes → tasks with owner matching", "Must", 800, 3, 0.8, 1, 7, "Done", "S5", "No task from non-actions"),
 ("Tasks", "Jira two-way sync", "Should", 300, 2, 0.5, 3, 3, "Backlog", "V1", "Status sync both directions"),
 ("Analytics", "Executive dashboard with deltas & drill-downs", "Must", 600, 2, 0.9, 2, 6, "Done", "S6", "Measured vs estimated labelled"),
 ("Analytics", "Mixpanel event forwarding", "Should", 1000, 1, 0.9, 0.5, 9, "Done (needs token)", "S6", "Insert-id dedupe"),
 ("Analytics", "Customer-facing ROI report", "Could", 400, 2, 0.5, 2, 5, "Backlog", "V1", "Validated time-saved method"),
 ("Billing", "Plans, limits, metering, trial", "Must", 1000, 3, 1.0, 2, 7, "Done", "S6", "402 at limit; monthly reset"),
 ("Billing", "Stripe checkout/portal/webhooks", "Must", 500, 3, 0.8, 1, 7, "Done (needs keys)", "S6", "Signature verified; idempotent invoices"),
 ("Billing", "Razorpay adapter (INR, GST invoices)", "Should", 400, 2, 0.7, 2, 6, "Backlog", "V1", "UPI/cards; GST invoice"),
 ("Billing", "AI credit packs (usage-based)", "Should", 300, 2, 0.6, 2, 5, "Backlog", "V1", "From financial model finding"),
 ("Integrations", "Catalogue + real connection tests + encryption", "Must", 500, 2, 0.9, 2, 6, "Done", "S6", "Connected only after successful call"),
 ("Integrations", "Slack notifications channel", "Should", 600, 1, 0.8, 1, 7, "Partially (connect)", "V1", "Workflow alerts post to Slack"),
 ("Notifications", "In-app + email with preferences", "Must", 1000, 1, 1.0, 1, 8, "Done", "S5", "Per-type channel toggles"),
 ("Admin", "Admin console (orgs, users, jobs, spend, flags, support)", "Must", 50, 2, 1.0, 2, 6, "Done", "S6", "Hidden 404 for non-admins"),
 ("Platform", "Postgres job queue + worker + scheduler", "Must", 1000, 2, 0.9, 1, 7, "Done", "S2", "SKIP LOCKED; backoff"),
 ("Platform", "Docker images, compose, CI", "Must", 1000, 1, 1.0, 1, 8, "Done", "S6", "Compose stack passes E2E"),
 ("Platform", "Postgres row-level security as defence in depth", "Should", 1000, 2, 0.6, 2, 4, "Backlog", "V1", "RLS policies on tenant tables"),
 ("Platform", "Error monitoring (Sentry) & tracing (OpenTelemetry)", "Should", 1000, 1, 0.9, 1, 7, "Backlog", "V1", "Errors with request ids"),
 ("AI Quality", "Golden eval set + runner + CI gate", "Must", 1000, 2, 0.9, 1, 7, "Done", "S6", "Report per run"),
 ("AI Quality", "Per-customer private eval sets", "Should", 200, 2, 0.6, 2, 5, "Backlog", "V1", "Design partner corpora"),
]

out = Path(__file__).resolve().parents[1] / "docs" / "product" / "backlog.csv"
with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Issue Type", "Summary", "Epic Link", "Priority", "MoSCoW", "Reach", "Impact", "Confidence", "Effort (pw)", "RICE", "ICE",
                "Status", "Sprint", "Acceptance Criteria", "Labels"])
    rows = []
    for e, s, m, r, i, c, ef, ease, st, sp, ac in B:
        rice = round(r * i * c / ef)
        ice = round(i / 3 * 10 * c * 10 * ease / 100, 1)  # impact(1-10) × confidence(1-10) × ease(1-10) / 100
        pr = {"Must": "Highest", "Should": "High", "Could": "Medium"}[m]
        rows.append(["Story", s, e, pr, m, r, i, c, ef, rice, ice, st, sp, ac, "nexora"])
    rows.sort(key=lambda x: -x[9])
    w.writerows(rows)
print(len(B), "stories ->", out)
for r in rows[:12]:
    print(r[9], r[10], r[1], r[11])
