# Handoff & Progress Log

## Completed (verified)
* Backend: 12 modules, 47 tables, 4 migrations, AI gateway (Anthropic/OpenAI/demo), RAG, agents, workflows, data, tasks, billing,
  integrations, notifications, analytics, admin, experiments, Postgres job queue/worker. 90 tests pass; ruff clean; pip-audit clean.
* Frontend: marketing + pricing, auth flows, 15 product screens, admin console, public forms; light/dark; responsive. tsc + build
  clean; npm audit clean; 6 unit tests; 8 E2E journeys pass on dev servers and on the Docker Compose production stack.
* Ops: Dockerfiles, compose (postgres/redis/migrate/api/worker/web/n8n), CI workflow, Dependabot, Postman/Newman suite, load test,
  analytics views + BI role, seed script, screenshot tour (27 screens, 0 console errors).
* AI eval framework with golden set, latest results committed, chunking sweep.
* All product/business/technical docs, financial model xlsx, backlog CSV, case study, executive deck, resume entry.

## Not done / blocked (requires external credentials or decisions)
| Item | Blocker | Next step |
|---|---|---|
| Real LLM end-to-end + real eval numbers | No `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` in this environment | Set keys, run `ai-engine/run_eval.py`, compare with demo baseline |
| Live deployment & domain | No cloud/Cloudflare credentials | Follow DEPLOYMENT_GUIDE §3/§8 |
| Stripe live checkout | No Stripe keys/prices | Create prices, set `STRIPE_*`, test webhooks with Stripe CLI |
| Razorpay adapter | Business decision + keys | Implement `billing_razorpay.py` mirroring `billing_stripe.py` |
| Google/Slack OAuth round-trip | OAuth client credentials | Configure redirect URIs `/api/hooks/oauth/*` |
| OCR | System packages (tesseract, poppler) | Add to backend image, `pip install pytesseract pdf2image` |
| Customer validation | Requires real interviews | MARKET_RESEARCH §6 plan |

## Known issues
See SECURITY_REVIEW §5 (RLS, nonce CSP, MFA, Redis required in prod) and TEST_REPORT §6.

## Next exact steps
1. Add Sentry + OpenTelemetry (backend `app/main.py` middleware, frontend `instrumentation.ts`).
2. Streaming chat via SSE: gateway `stream()` per provider, `/conversations/{id}/messages/stream`.
3. Postgres RLS: `SET LOCAL app.org_id` in `get_org_context` + policies per tenant table; keep app checks.
4. Implement plan change D-012 (Pro 5,000 messages + credit packs) behind a feature flag; grandfather existing orgs.
5. Run real-provider evals and update AI_EVALUATION_FRAMEWORK.md.

## Architecture pointers
Start at `backend/app/main.py` → `core/deps.py` (auth/tenancy) → `ai/gateway.py` → `rag/retrieval.py` → `agents/runtime.py` →
`workflows/service.py`. Frontend: `src/lib/{api,auth,hooks}.ts(x)` → `src/components/app/shell.tsx` → `src/app/app/*`.
