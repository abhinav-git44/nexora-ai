# Release Notes

## v1.0.0 — 2 Nov 2026 (first complete build)
**Highlights**
* AI Business Assistant with grounded, cited answers; summarise / extract / report modes; sharing and export.
* Knowledge base for PDF, DOCX, XLSX, CSV, TXT and Markdown with hybrid retrieval, reranking, versioning, role-based access and
  prompt-injection defence.
* Agent Studio: 8 templates, 12 tools, persisted multi-step runs, human approvals, metrics.
* Visual workflow builder: 20 node types, versioned publishing, HMAC webhooks, hosted forms, schedules, document triggers, approvals,
  retries and analytics; n8n node.
* Data intelligence: dataset profiling, NL→SQL with an AST safety guard, charts, exports, reports, Power BI views.
* Tasks with board/list/calendar and AI extraction from meeting notes.
* Executive analytics with North Star, measured vs estimated metrics, drill-downs.
* Plans, metering, reverse trial, Stripe adapter (demo mode without keys), integrations hub, notifications, admin console.
* Docker images, Compose stack, CI pipeline, AI evaluation runner, Postman suite.

**Known limitations** — see TEST_REPORT.md §6 and SECURITY_REVIEW.md §5 (no real-provider E2E in this environment, RLS and MFA
planned, Razorpay planned, OCR needs system packages).
