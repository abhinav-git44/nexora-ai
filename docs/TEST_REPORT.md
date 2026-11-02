# Test Report — V1

Date: 2 Nov 2026 · Environment: cloud dev container (4 vCPU), PostgreSQL 16 + pgvector 0.6, Redis 7, Python 3.13, Node 22,
Chromium (Playwright). AI provider: **demo engine** (no API keys available) — real-provider adapters covered by unit tests with mocks.

## 1. Summary
| Suite | Tool | Result |
|---|---|---|
| Backend unit + integration | pytest | **90 passed**, 0 failed · 78% line coverage |
| Frontend unit | Vitest | **6 passed** |
| End-to-end (critical journeys) | Playwright | **8/8 passed** on dev servers **and** on the production Docker Compose stack |
| API contract smoke | Postman/Newman | **21 requests, 20 assertions, 0 failures** |
| AI evaluation | `ai-engine/run_eval.py` | 28/29 cases pass (demo engine; see AI_EVALUATION_FRAMEWORK.md) |
| Performance | `tests/performance/load_test.py` | 0% errors at 20 concurrency (table §4) |
| Dependency scanning | pip-audit / npm audit | 0 known vulnerabilities (after fix) |
| Static checks | ruff, `tsc --noEmit`, `next build` | clean |
| UI console errors | Playwright screenshot tour (27 screens) | **0** |

## 2. Coverage by requirement area
| Area | Tests |
|---|---|
| Auth | register/login/lockout/refresh rotation & replay/session revoke/verification/reset/profile/export/delete guard |
| Tenancy & RBAC | cross-tenant 404s across 8 modules, header spoofing, RAG isolation, 5-role permission matrix, deactivation, last-owner, document role restriction |
| Knowledge/RAG | 6 formats indexed (incl. generated PDF/DOCX/XLSX), hybrid/vector/keyword search, cited answer, filters, injection flagging & neutralisation, validation (fake PDF, exe, empty, corrupt DOCX), duplicates, versions, re-index, delete |
| Assistant | RAG conversation + metering, plan limit 402, read-only sharing, summarise/extract/recommend, input validation |
| AI layer | cost maths, Anthropic & OpenAI message conversion (tool results grouping, thinking replay), provider fallback, non-retryable stop, demo fallback, response cache, routing table, safety controls, PII redaction before provider, demo tool selection |
| Agents | template run with tools, async worker run, approval → approve (role-checked, single decision) → resume, reject path, tool validation & plan gate, viewer blocked, safe calculator |
| Workflows | validation (trigger, cycle, cron spacing, required fields), branching + versioning, failure + retry, approval & delay resume, loop/branch/filter, HMAC webhook (missing/bad/valid), hosted form, document-uploaded trigger, plan-gated nodes |
| Data | 20 destructive/escape SQL patterns rejected, rewrite + limit clamp, ingest/profile/quality, 3 NL queries, unsafe manual SQL, CSV/XLSX export, report, preview, feature gate, XLSX ingest, CSV formula-injection escaping |
| Tasks & billing | CRUD, comments, activity, attachments, notifications, cross-org assignee blocked, AI extraction (no false tasks, urgent priority), plans, demo upgrade + invoice, enterprise contact-sales, downgrade guard, trial expiry |
| Security/admin/analytics | rate limiting, headers, SSRF, webhook node SSRF, encrypted credentials, never-connected-without-test, admin hidden + suspend, feature flags, support, audit log plan gate, dashboard numbers vs activity, sticky experiments, org deletion workflow |

## 3. E2E journeys (Playwright)
Sign-up → workspace · upload & index · cited answer · agent from template · publish → run → approve workflow · task create → done ·
demo-billing upgrade · admin console hidden & unauthenticated API rejected.

## 4. Performance (single uvicorn worker, dev DB, 20 concurrent clients)
| Endpoint | Requests | RPS | p50 | p95 | Errors |
|---|---|---|---|---|---|
| GET /api/health | 200 | 426 | 39 ms | 92 ms | 0% |
| GET /api/tasks | 200 | 104 | 182 ms | 264 ms | 0% |
| POST /api/documents/search (hybrid RAG) | 200 | 106 | 180 ms | 243 ms | 0% |
| GET /api/analytics/dashboard | 50 | 35 | 286 ms | 319 ms | 0% |
| POST /api/datasets/{id}/sql (guarded) | 50 | 69 | 142 ms | 167 ms | 0% |
Caveats: single worker; small dataset; LLM latency excluded (demo engine). Production sizing should use ≥2 workers per API container.
Background indexing of a short document completes in ~1–3 s end-to-end (E2E observes "indexed" within the 4 s test).

## 5. Defects found and fixed during testing
| # | Severity | Defect | Found by | Fix |
|---|---|---|---|---|
| 1 | High | `Document.deleted_at` column missing → upload crashed | tenancy tests | Model + migration |
| 2 | High | Autogenerate migration dropped hand-made HNSW indexes | migration review | Excluded manual indexes in Alembic `include_object` |
| 3 | Medium | Response cache duplicate-key error for identical requests in one transaction | AI unit test | Flush after cache write |
| 4 | Medium | Citation verification missed markers placed after full stops | RAG test | Normalise marker position |
| 5 | Medium | Neutraliser echoed the injected text inside its placeholder | injection test | Replace without echo |
| 6 | Medium | Number extraction picked "-77" from "INV-77" | extraction test | Field-anchored number parsing |
| 7 | Medium | Form labels not associated with inputs (a11y) | Playwright `getByLabel` | `Field` auto-binds ids |
| 8 | Low | Switch knob overlapped its label; logo invisible on mobile (duplicate SVG id); truncated select | screenshot review | CSS/SVG fixes |
| 9 | Low | Signed-out pages issued a refresh request → console 401 | console audit | Session hint flag |
| 11 | Medium | 24h response cache served results computed by older prompt/engine logic | screenshot review of an agent run | Cache key now includes `CACHE_VERSION` + route model candidates |
| 12 | Low | Demo task extractor kept instruction preambles in titles and read "Action:" as an owner | screenshot review | Preamble stripping + label-word filter; regression test |
| 10 | High (supply chain) | Vulnerable `postcss` via Next.js | npm audit | `overrides` pin, build + E2E re-verified |

No known critical or high defects remain open.

## 6. Not tested / limitations
Real LLM providers end-to-end (no keys) · Stripe live checkout (no keys; webhook handler unit-covered via signature logic) ·
email delivery via SMTP/Resend · OCR · Google/Slack OAuth round-trips · load beyond 20 concurrent users · cross-browser (Chromium
only) · formal accessibility audit (WCAG) beyond semantic labels/keyboard dialogs.
