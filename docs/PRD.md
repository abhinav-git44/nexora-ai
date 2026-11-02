# Product Requirements Document — NEXORA AI v1.0

| Field | Value |
|---|---|
| Owner | Product (author of this repository) |
| Status | V1 implemented; validation with design partners pending |
| Related | PRODUCT_STRATEGY.md · PRIORITISATION.md · TECHNICAL_ARCHITECTURE.md · TEST_REPORT.md |

## 1. Problem & goals
Ops-heavy small teams lose time answering repeated questions, chasing follow-ups and hand-building reports, and they cannot adopt
AI safely because generic tools are ungrounded and ungoverned. **Goal:** deliver a governed workspace where knowledge answers,
task capture, approval-gated automation and data questions work end-to-end, with measured outcomes and cost.

**Non-goals (V1):** CRM/ERP replacement; real-time co-editing; on-prem enterprise SSO; mobile apps (responsive web only);
autonomous multi-agent planning.

## 2. Success metrics
North Star: **Weekly successful AI-assisted business outcomes** (definition in ANALYTICS_FRAMEWORK.md). Guardrails: answer
correctness ≥ 85% on eval sets, hallucination rate on unanswerable questions ≤ 5%, workflow success ≥ 97%, gross margin ≥ 65%,
zero cross-tenant data exposure.

## 3. Functional requirements (status = implemented in this repo unless noted)
| ID | Requirement | Priority | Status |
|---|---|---|---|
| **M1 Auth & users** ||||
| FR-1.1 | Email/password registration with password policy; email verification; password reset (single-use, 1h) | Must | ✅ |
| FR-1.2 | Login with lockout after 5 failures; rotating refresh tokens (httpOnly cookie); session list & revoke | Must | ✅ |
| FR-1.3 | Organisations, multiple per user; invitations (7-day, role-bounded); workspaces | Must | ✅ |
| FR-1.4 | Roles Owner/Admin/Manager/Member/Viewer + platform Super Admin; server-side permission checks | Must | ✅ |
| FR-1.5 | Profile, password change (revokes other sessions), data export, account deletion (anonymise), org deletion with 7-day grace | Must | ✅ |
| FR-1.6 | Google sign-in when configured | Should | ✅ adapter (needs credentials) |
| **M2 Assistant** ||||
| FR-2.1 | Multi-conversation chat with history, auto-titles, context truncation | Must | ✅ |
| FR-2.2 | Knowledge-grounded answers with inline citations & verification | Must | ✅ |
| FR-2.3 | File upload in chat (scopes answers to attached files) | Must | ✅ |
| FR-2.4 | Summarise, structured extraction (user-defined fields), report mode, deep-analysis mode | Must | ✅ |
| FR-2.5 | Task recommendations from a conversation (review before create) | Should | ✅ |
| FR-2.6 | Export (Markdown/JSON), read-only sharing with org members, feedback | Should | ✅ |
| FR-2.7 | Provider abstraction (Anthropic, OpenAI, demo), routing, fallback, token & cost tracking | Must | ✅ |
| **M3 Knowledge & RAG** ||||
| FR-3.1 | PDF, DOCX, TXT, CSV, XLSX, MD upload with validation (magic bytes, zip-bomb, macro rejection, size) | Must | ✅ |
| FR-3.2 | Extraction, configurable chunking, embeddings (versioned), pgvector + full-text hybrid search, reranking | Must | ✅ |
| FR-3.3 | Metadata filters (doc ids, file types, tags), retrieval playground | Should | ✅ |
| FR-3.4 | Document permissions (min role + allowed users) enforced in SQL | Must | ✅ |
| FR-3.5 | Versioning, re-index (strategy switch), deletion (chunks + files) | Must | ✅ |
| FR-3.6 | Prompt-injection detection, neutralisation, ranking penalty | Must | ✅ |
| FR-3.7 | OCR for scanned PDFs | Could | ⚠️ adapter; requires tesseract install |
| **M4 Agent Studio** ||||
| FR-4.1 | Configure name, instructions, model route, tools, approvals, memory, step & token limits, output format/schema | Must | ✅ |
| FR-4.2 | 8 templates | Must | ✅ |
| FR-4.3 | Multi-step tool calling, persisted state, retries, execution logs, human approval/reject → resume | Must | ✅ |
| FR-4.4 | Per-agent performance metrics (success, duration, cost, tool errors) | Should | ✅ |
| **M5 Workflows** ||||
| FR-5.1 | Drag-and-drop builder, 20 node types (5 triggers, 9 actions, 6 logic) | Must | ✅ |
| FR-5.2 | Validation (single trigger, cycles, required fields, cron spacing, plan-gated nodes) | Must | ✅ |
| FR-5.3 | Publish versions, restore, pause; executions run the version live at start | Must | ✅ |
| FR-5.4 | Manual, schedule, HMAC webhook, hosted form, document-uploaded triggers | Must | ✅ |
| FR-5.5 | Execution history with per-node logs, retry failed, analytics | Must | ✅ |
| FR-5.6 | n8n integration node | Should | ✅ (needs an n8n instance) |
| **M6 Data intelligence** ||||
| FR-6.1 | CSV/XLSX ingest, type inference, column roles, profiling, cleaning recommendations | Must | ✅ |
| FR-6.2 | NL → SQL with AST validation, read-only execution, timeout, row limit; editable SQL | Must | ✅ |
| FR-6.3 | Charts, CSV/XLSX export (formula-injection safe), report generation | Must | ✅ |
| FR-6.4 | Power BI connection via read-only role & analytics views | Should | ✅ (instructions + views) |
| **M7 Tasks** | CRUD, assignee (members only), priority, due, labels, comments, attachments, activity, board/list/calendar, AI extraction & summary | Must | ✅ |
| **M8 Dashboard** | KPIs with previous-period deltas, day/week/month trends, drill-downs, CSV export, measured vs estimated | Must | ✅ |
| **M9 Billing** | Plans, limits, metering, trial, upgrade/downgrade guard, invoices, Stripe adapter + webhooks, demo mode | Must | ✅ (Stripe needs keys) |
| **M10 Integrations** | Catalogue, real connection tests, encrypted credentials, OAuth (Google/Slack), logs, revoke | Must | ✅ |
| **M11 Notifications** | In-app + email per-type preferences, read/unread, approvals/task/workflow/agent alerts | Must | ✅ |
| **M12 Admin** | Org/user mgmt, subscription override & suspension, usage & AI spend, health, failed jobs retry, audit, flags, support | Must | ✅ |

## 4. Non-functional requirements
| Area | Requirement | Verification |
|---|---|---|
| Security | Tenant isolation on every query/job/retrieval; 404 on foreign ids | `test_tenancy_rbac.py`, E2E |
| Security | Secrets server-side only; credentials encrypted at rest | `test_security_admin_analytics.py`, code review |
| Performance | p95 < 300 ms for CRUD/search at 20 concurrent users on one worker | `tests/performance/results.json` |
| Reliability | Job retries with exponential backoff; resumable workflows/agents | Workflow & agent tests |
| Accessibility | Labels bound to inputs, keyboard dialogs (native `<dialog>`), focus rings, reduced motion | E2E uses accessible locators |
| Responsiveness | 390px mobile to 1440px desktop | Screenshots 30–32 |
| Observability | Request ids, structured logs, AI request ledger, admin health | Admin console |
| Privacy | Data export, deletion, retention via org purge, DPDP-aligned notices | SECURITY_REVIEW.md |

## 5. User stories & acceptance criteria (representative)
**US-01 Cited answer.** *As an ops manager I want answers from our documents with sources so I can trust and verify them.*
- Given an indexed policy, when I ask a covered question, then the answer includes ≥1 citation chip linking to that document.
- Given no relevant document, then the assistant says it could not find the information (no invented facts).
- Given a document restricted to managers, a member's answer never cites it.

**US-02 Notes → tasks.** *As a manager I want action items extracted from meeting notes so nothing is dropped.*
- Suggestions show title, owner (matched to a member when possible), due date (parsed), priority; nothing is created until I confirm.
- Lines without an action (e.g. "discussed hiring plan") are not turned into tasks.

**US-03 Approval-gated automation.** *As a manager I want risky steps to wait for approval.*
- A run reaching an Approval node shows status *waiting approval*; managers are notified; members cannot decide.
- Approve continues along the *approved* branch; reject along *rejected*; each decision is audit-logged.

**US-04 Safe data questions.** *As an analyst I want SQL I can trust.*
- Generated SQL is shown; DELETE/DROP/multi-statement/other tables are rejected with a reason; results are limited to 1,000 rows.

**US-05 Plan enforcement.** *As the business, limits must block rather than overcharge.*
- At the monthly AI message limit, new messages return a clear 402 with an upgrade action; usage resets monthly.

(Full backlog with 60+ stories: `docs/product/backlog.csv`, importable into Jira.)

## 6. API specification
OpenAPI 3.1 generated from code: `docs/openapi.json` (148 paths / 178 operations). Overview in API_DOCUMENTATION.md.

## 7. Dependencies & risks
LLM provider availability (mitigated by fallback + demo), pgvector performance at scale (HNSW indexes per embedding model), email
deliverability (Resend/SMTP adapter), payment provider (Stripe now, Razorpay planned for India). Full risk register in PRODUCT_ROADMAP.md.

## 8. Release criteria (V1)
All P0 requirements implemented; 90 backend tests, 6 frontend unit tests, 8 E2E journeys, Newman suite and eval run green; no open
critical/high security findings; production build and container stack verified. Status: **met** (see TEST_REPORT.md).
