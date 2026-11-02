# Technical Architecture

## 1. System context
```mermaid
flowchart LR
  U[Browser<br/>Next.js app] -- "/api/* (same origin)" --> W[Next.js server<br/>rewrites + security headers]
  W --> A[FastAPI modular monolith]
  A --> PG[(PostgreSQL 16<br/>+ pgvector)]
  A --> R[(Redis<br/>rate limits)]
  A --> S[(Object storage<br/>local / Cloudflare R2)]
  WK[Worker process<br/>job queue + scheduler] --> PG
  WK --> S
  A & WK --> GW{{AI gateway}}
  GW --> AN[Anthropic Messages API]
  GW --> OA[OpenAI Responses API]
  GW --> DM[Demo engine (local)]
  WK --> MX[Mixpanel]
  A --> ST[Stripe]
  WK --> N8[n8n / webhooks / email]
  BI[Power BI] -. read-only role .-> PG
```

## 2. Why a modular monolith
| Option | Pros | Cons | Decision |
|---|---|---|---|
| Microservices (auth, rag, agents, workflows…) | Independent scaling | Distributed transactions for tenant data, 5× ops cost, slower iteration for a small team | ❌ |
| **Modular monolith** + separate worker process | One deploy, ACID across modules, simple local dev; worker scales independently | Discipline needed to keep boundaries | ✅ |
Boundaries: each bounded context is a package (`app/modules/<x>.py` API + `app/<x>/` domain: `rag`, `agents`, `workflows`, `data`,
`integrations`, `ai`). Modules talk through Python functions, not HTTP; any of `rag`, `workflows` or `agents` can be extracted later
because they depend only on `core` + models.

## 3. Backend layout
```
backend/app/
  core/        config · db · deps (auth + OrgContext) · permissions (RBAC) · plans (limits/metering) · ratelimit · audit/analytics
               crypto (Fernet) · security (argon2, JWT, HMAC) · netguard (SSRF) · storage (local/R2) · email
  ai/          catalog (models, prices, routes) · gateway (routing, fallback, caching, metering) · safety · providers/{anthropic,openai,demo}
  rag/         extraction · chunking · embeddings · retrieval (hybrid + rerank + citations) · indexing (job)
  agents/      tools (registry, permissions) · templates · runtime (persisted state machine)
  workflows/   nodes (catalogue, templating, conditions) · service (validate, publish, executor, triggers) · templates
  data/        sqlguard (AST validation) · nl2sql_rules (demo) · service (ingest, profile, execute read-only)
  modules/     FastAPI routers: auth, orgs, notifications, knowledge, chat, agents, workflows, data, tasks, billing,
               integrations, analytics, admin, public (webhooks/forms), experiments
  worker/      queue (Postgres SKIP LOCKED, retries/backoff) · run (process entrypoint) · misc jobs
```

## 4. Request lifecycle & tenant isolation
1. Middleware: request id, global per-IP rate limit, security headers, structured access log.
2. `get_current_user`: JWT verified **and** the bound `user_sessions` row must be live (revocation is immediate).
3. `get_org_context`: `X-Org-Id` → active membership required → `OrgContext(user, org, membership)`; suspended/deleted orgs blocked.
4. `require("perm")`: role ≥ permission's minimum (deny-by-default for unknown permissions).
5. Handlers load rows by id **and** compare `row.org_id == ctx.org_id` → 404 otherwise; list queries filter by `org_id`.
6. Background jobs carry `org_id`; handlers re-check `row.org_id == job.org_id`.
7. Retrieval filters tenancy and document role **inside the SQL** (`ACCESS_SQL` in `rag/retrieval.py`).
Defence-in-depth planned: Postgres RLS policies keyed on `SET LOCAL app.org_id` (roadmap V1).

## 5. Asynchronous processing
Postgres-backed queue (`jobs` table, `FOR UPDATE SKIP LOCKED`), exponential backoff, stale-lock recovery, scheduler tick every 15s
for cron workflows. Runs in-process for dev, or as `python -m app.worker.run` (compose `worker` service). Redis is deliberately
**not** a queue dependency: one fewer stateful system to operate; throughput target (hundreds of jobs/minute) is well within
Postgres capacity. Revisit at >50 jobs/s.

## 6. Frontend
Next.js 15 App Router, React 19, TypeScript strict, Tailwind v4 design tokens (light/dark), custom shadcn-style components,
Recharts, React Flow (`@xyflow/react`), SWR with **org-scoped keys** (switching org never shows stale tenant data). Access token
in memory only; refresh via httpOnly cookie. All API calls go through the Next.js rewrite → no CORS, no API keys in the browser, CSP
`connect-src 'self'`.

## 7. Deployment topology (recommended)
Cloudflare (DNS, WAF, TLS, caching of static assets) → web (Next.js standalone container) → api (2+ uvicorn workers) + worker
(1+), managed Postgres with pgvector (e.g. Neon/Supabase/RDS), managed Redis, Cloudflare R2 for files. Migrations run as a one-off
release step (`migrate` service). Details in DEPLOYMENT_GUIDE.md.

## 8. Key trade-offs
| Decision | Trade-off accepted |
|---|---|
| Sync SQLAlchemy + threadpool | Simpler code and transactions; async not needed at current scale; LLM latency dominates |
| Dimension-less vector column | Must cast in queries to use per-model HNSW indexes; gains painless embedding migrations |
| Own agent state machine instead of LangGraph | Less framework leverage; full control of persistence, approvals and audit (D-007) |
| Hard plan limits | Possible friction at limit; predictable cost for SMBs |
| Local deterministic demo engine | Not an LLM; makes every flow testable/keyless and CI-safe, always labelled |
