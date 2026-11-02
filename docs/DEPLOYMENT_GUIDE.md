# Deployment Guide

## 1. Local development
```bash
# prerequisites: Python 3.12+, Node 22, PostgreSQL 16 with pgvector, Redis
createdb nexora && psql nexora -c "CREATE EXTENSION vector"
cp .env.example .env            # fill JWT_SECRET / ENCRYPTION_KEY (commands inside the file)
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000        # in-process worker starts automatically
.venv/bin/python ../scripts/seed_demo.py                     # optional demo org (labelled DEMO)
cd ../frontend && npm ci && npm run dev                       # http://localhost:3000
```
Demo logins after seeding: `demo.owner@example.com` / `DemoPassw0rd!` (also `demo.manager@`, `demo.member@`); platform admin
`admin@example.com` (needs `SUPER_ADMIN_EMAILS=admin@example.com` at signup time).

## 2. Docker Compose (verified)
```bash
cp .env.example .env   # set JWT_SECRET, ENCRYPTION_KEY, APP_ENV=production, APP_BASE_URL
docker compose -f deployment/docker-compose.yml --env-file .env up -d --build
# services: postgres(pgvector) · redis · migrate (alembic, one-off) · api · worker · web  [+ n8n with --profile automation]
```
Verified in this project: images build, migrations run, API healthy, and all 8 Playwright journeys pass against the compose stack
in `APP_ENV=production`. Behind a corporate proxy, pass `--build-arg HTTPS_PROXY=… --secret id=extra_ca,src=ca.crt`.

## 3. Production reference architecture
| Layer | Recommendation |
|---|---|
| Edge | **Cloudflare**: DNS, TLS, WAF managed rules, rate limiting on `/api/auth/*`, Turnstile on signup, cache static `/_next/static/*` |
| Web | `nexora/web` container (Next.js standalone) on Cloud Run / Fly.io / Render / ECS; `BACKEND_URL` baked at build or set per env |
| API | `nexora/backend` ≥2 replicas, 2 uvicorn workers each; health `GET /api/health` |
| Worker | same image, `python -m app.worker.run`, ≥1 replica (`RUN_WORKER_IN_PROCESS=false` on API) |
| Database | Managed Postgres 16 with pgvector (Neon, Supabase, RDS, Cloud SQL); PITR backups ≥7 days; read-only role for BI |
| Cache | Managed Redis (rate limits) |
| Files | Cloudflare R2 (`STORAGE_BACKEND=r2`, bucket private) |
| Email | Resend or SMTP (`EMAIL_BACKEND`) with SPF/DKIM/DMARC |
| Secrets | Platform secret manager; never in images; rotate JWT secret (invalidates sessions) and Fernet key (re-encrypt) |

## 4. Release process
1. CI green (lint, tests, build, eval, audits, E2E on compose).
2. Build & push images tagged with the git SHA.
3. Run `migrate` (alembic upgrade head) as a one-off job — migrations are additive; destructive changes use expand/contract.
4. Roll out API/worker/web; verify `/api/health`, admin System health, error rates.
5. Roll back by redeploying the previous SHA (migrations remain backward compatible within one release).

## 5. Environment configuration
All variables are documented in `.env.example`. Production must set: `APP_ENV=production`, `JWT_SECRET`, `ENCRYPTION_KEY`,
`COOKIE_SECURE=true`, `APP_BASE_URL`, `API_BASE_URL`, `DATABASE_URL`, `REDIS_URL`; optionally AI keys, Stripe, Mixpanel, R2, email,
OAuth. The API refuses to start in production with the default JWT secret; credential encryption refuses without `ENCRYPTION_KEY`.

## 6. Monitoring
Built in: request-id logs, `ai_requests` ledger, admin console (health, failed jobs, workflow failures, AI spend), `/api/health`.
Recommended: Sentry (backend + frontend), OpenTelemetry traces, uptime probe on `/api/health`, alerts on job failures > 5/10 min,
AI error rate > 5%, daily AI spend > budget.

## 7. Power BI
Apply `deployment/sql/readonly_role.sql` (creates `nexora_bi`, read-only, 15s timeout), then Power BI Desktop → Get Data →
PostgreSQL → server/database → schema `analytics` (views: `north_star_weekly`, `activation_funnel`, `retention_cohorts`,
`ai_usage_daily`, `cost_per_outcome_weekly`, `workflow_reliability_daily`, `feature_adoption_weekly`, `mrr_by_plan`,
`experiment_exposure`) or per-dataset tables in schema `datasets`.

## 8. Domain & live deployment status
No cloud credentials or domain were available in this build environment, so **no public deployment exists**. The deployable path
(images + compose + CI) is verified locally. To go live: create a Cloudflare zone, deploy the images to a container host, point
`app.<domain>` at the web service, set `APP_BASE_URL=https://app.<domain>`, `COOKIE_SECURE=true`.
