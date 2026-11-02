# API Documentation

* **Base URL:** `/api` (the web app proxies `/api/*` to FastAPI, so browsers only talk to one origin).
* **Interactive docs:** `GET /docs` (Swagger UI) and `GET /redoc` on the API; machine-readable spec: [`openapi.json`](openapi.json).
* **Postman:** [`../tests/postman/nexora.postman_collection.json`](../tests/postman/nexora.postman_collection.json) — run with Newman.

## Authentication
1. `POST /api/auth/register` or `POST /api/auth/login` → `{access_token, expires_in, user}` and an **httpOnly** `nx_refresh` cookie
   (path `/api/auth`, SameSite=Lax, Secure in production).
2. Send `Authorization: Bearer <access_token>` (15-minute JWT, bound to a server-side session).
3. `POST /api/auth/refresh` rotates the refresh token and returns a new access token; replaying an old refresh token fails.
4. **Tenant context:** every organisation-scoped endpoint requires `X-Org-Id: <uuid>`. Membership is verified on each request;
   non-members get **404** (no existence leak). Super-admin endpoints under `/api/admin` return 404 to everyone else.

## Errors
```json
{ "error": { "code": "plan_limit_reached", "message": "Plan limit reached for ai messages (150/150)…", "details": { "metric": "ai_messages", "used": 150, "limit": 150 } } }
```
| Status | Codes |
|---|---|
| 400 | `bad_request`, `invalid_token`, `unsupported_file_type`, `invalid_workflow`, `unsafe_sql`, `downgrade_blocked` |
| 401 | `unauthenticated`, `invalid_token`, `session_revoked`, `invalid_signature` |
| 402 | `plan_limit_reached` (with feature or metric) |
| 403 | `forbidden` (role), `email_unverified`, `org_suspended` |
| 404 | `not_found` (also for other tenants' resources) |
| 409 | `email_taken`, `duplicate_document`, `already_member` |
| 422 | `validation_error` (`details.fields[]`) |
| 423 | `account_locked` |
| 429 | `rate_limited` (`details.retry_after_s`) |
| 503 | `ai_unavailable` (all providers failed) |

## Webhooks
* **Workflow webhook trigger:** `POST /api/hooks/workflows/{token}` with header `X-Nexora-Signature: sha256=<hex HMAC-SHA256 of raw body>`
  using the workflow's signing secret → `202 {execution_id}`.
* **Hosted forms:** `GET/POST /api/forms/{token}` (rate-limited, honeypot).
* **Stripe:** `POST /api/hooks/stripe` (signature verified with `STRIPE_WEBHOOK_SECRET`, 5-minute tolerance).
* **OAuth callbacks:** `GET /api/hooks/oauth/{google|slack}`.

## Conventions
JSON everywhere except uploads (`multipart/form-data`) and exports (`text/csv`, XLSX, Markdown). Timestamps ISO-8601 UTC. Long
operations (indexing, agent runs, workflow executions) return immediately with a `queued` status; poll the resource
(`sync: true` exists for tests and the console).

<!-- GENERATED -->
## Endpoint index (generated from OpenAPI)

### admin

| Method | Path | Summary |
|---|---|---|
| GET | `/api/admin/ai-usage` | Ai Usage |
| GET | `/api/admin/audit-logs` | Audit Logs |
| GET | `/api/admin/feature-flags` | Flags |
| PUT | `/api/admin/feature-flags` | Upsert Flag |
| GET | `/api/admin/jobs` | Jobs |
| POST | `/api/admin/jobs/{job_id}/retry` | Retry Job |
| GET | `/api/admin/orgs` | Orgs |
| GET | `/api/admin/orgs/{org_id}` | Org Detail |
| PATCH | `/api/admin/orgs/{org_id}` | Update Org |
| GET | `/api/admin/overview` | Overview |
| GET | `/api/admin/product-metrics` | Product Metrics |
| GET | `/api/admin/support-tickets` | Tickets |
| PATCH | `/api/admin/support-tickets/{tid}` | Update Ticket |
| GET | `/api/admin/users` | Users |
| PATCH | `/api/admin/users/{user_id}` | Update User |
| GET | `/api/admin/workflow-failures` | Workflow Failures |

### agents

| Method | Path | Summary |
|---|---|---|
| GET | `/api/agents` | List Agents |
| POST | `/api/agents` | Create Agent |
| POST | `/api/agents/from-template/{key}` | From Template |
| GET | `/api/agents/runs/{run_id}` | Get Run |
| POST | `/api/agents/runs/{run_id}/cancel` | Cancel Run |
| GET | `/api/agents/templates` | Templates |
| GET | `/api/agents/tools` | Tools |
| DELETE | `/api/agents/{agent_id}` | Archive Agent |
| GET | `/api/agents/{agent_id}` | Get Agent Ep |
| PUT | `/api/agents/{agent_id}` | Update Agent |
| POST | `/api/agents/{agent_id}/memory/clear` | Clear Memory |
| GET | `/api/agents/{agent_id}/metrics` | Agent Metrics |
| GET | `/api/agents/{agent_id}/runs` | List Runs |
| POST | `/api/agents/{agent_id}/runs` | Run Agent |

### analytics

| Method | Path | Summary |
|---|---|---|
| GET | `/api/analytics/ai-usage` | Ai Usage |
| GET | `/api/analytics/dashboard` | Dashboard |
| GET | `/api/analytics/drilldown` | Drilldown |
| GET | `/api/analytics/export` | Export |
| GET | `/api/analytics/timeseries` | Timeseries |

### approvals

| Method | Path | Summary |
|---|---|---|
| GET | `/api/approvals` | List Approvals |
| POST | `/api/approvals/{approval_id}/decide` | Decide |

### assistant

| Method | Path | Summary |
|---|---|---|
| POST | `/api/assistant/extract` | Extract Structured |
| GET | `/api/assistant/models` | Models |
| POST | `/api/assistant/recommend-tasks` | Recommend Tasks |
| POST | `/api/assistant/summarize` | Summarize |
| GET | `/api/conversations` | List Conversations |
| POST | `/api/conversations` | Create Conversation |
| POST | `/api/conversations/messages/{msg_id}/feedback` | Feedback |
| DELETE | `/api/conversations/{conv_id}` | Delete Conversation |
| GET | `/api/conversations/{conv_id}` | Get Conversation |
| PATCH | `/api/conversations/{conv_id}` | Update Conversation |
| POST | `/api/conversations/{conv_id}/attachments` | Attach |
| GET | `/api/conversations/{conv_id}/export` | Export |
| POST | `/api/conversations/{conv_id}/messages` | Send Message |
| POST | `/api/conversations/{conv_id}/share` | Share |
| DELETE | `/api/conversations/{conv_id}/share/{user_id}` | Unshare |

### auth

| Method | Path | Summary |
|---|---|---|
| POST | `/api/auth/change-password` | Change Password |
| POST | `/api/auth/forgot-password` | Forgot Password |
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/auth/me` | Me |
| PATCH | `/api/auth/me` | Update Profile |
| POST | `/api/auth/me/delete` | Delete Account |
| GET | `/api/auth/me/export` | Export My Data |
| POST | `/api/auth/me/onboarding-complete` | Onboarding Complete |
| GET | `/api/auth/oauth/google/callback` | Google Callback |
| GET | `/api/auth/oauth/google/start` | Google Start |
| GET | `/api/auth/providers` | Auth Providers |
| POST | `/api/auth/refresh` | Refresh |
| POST | `/api/auth/register` | Register |
| POST | `/api/auth/reset-password` | Reset Password |
| GET | `/api/auth/sessions` | List Sessions |
| DELETE | `/api/auth/sessions/{session_id}` | Revoke Session |
| POST | `/api/auth/verify-email/confirm` | Confirm Verification |
| POST | `/api/auth/verify-email/request` | Request Verification |

### billing

| Method | Path | Summary |
|---|---|---|
| POST | `/api/billing/cancel` | Cancel |
| POST | `/api/billing/change-plan` | Change Plan |
| GET | `/api/billing/invoices` | Invoices |
| GET | `/api/billing/plans` | Plans |
| POST | `/api/billing/portal` | Portal |
| POST | `/api/billing/resume` | Resume |
| GET | `/api/billing/subscription` | Subscription |
| GET | `/api/billing/usage` | Usage |

### data

| Method | Path | Summary |
|---|---|---|
| GET | `/api/datasets` | List Datasets |
| POST | `/api/datasets` | Upload |
| GET | `/api/datasets/queries/{query_id}/export` | Export |
| DELETE | `/api/datasets/{ds_id}` | Delete Dataset |
| GET | `/api/datasets/{ds_id}` | Get Dataset |
| GET | `/api/datasets/{ds_id}/powerbi` | Powerbi |
| GET | `/api/datasets/{ds_id}/preview` | Preview |
| GET | `/api/datasets/{ds_id}/queries` | History |
| POST | `/api/datasets/{ds_id}/query` | Nl Query |
| POST | `/api/datasets/{ds_id}/report` | Report |
| POST | `/api/datasets/{ds_id}/sql` | Run Sql |

### experiments

| Method | Path | Summary |
|---|---|---|
| GET | `/api/experiments/assignments` | Assignments |
| GET | `/api/experiments/results` | Results |
| POST | `/api/experiments/{key}/exposure` | Exposure |

### integrations

| Method | Path | Summary |
|---|---|---|
| GET | `/api/integrations` | List Integrations |
| GET | `/api/integrations/n8n/workflows` | N8N Workflows |
| DELETE | `/api/integrations/{provider}` | Disconnect |
| POST | `/api/integrations/{provider}/connect` | Connect |
| GET | `/api/integrations/{provider}/logs` | Logs |
| GET | `/api/integrations/{provider}/oauth/start` | Oauth Start |
| POST | `/api/integrations/{provider}/test` | Test |

### knowledge

| Method | Path | Summary |
|---|---|---|
| GET | `/api/documents` | List Documents |
| POST | `/api/documents` | Upload |
| POST | `/api/documents/ask` | Ask |
| POST | `/api/documents/search` | Search |
| GET | `/api/documents/stats` | Stats |
| DELETE | `/api/documents/{doc_id}` | Delete Document |
| GET | `/api/documents/{doc_id}` | Get Document |
| PATCH | `/api/documents/{doc_id}` | Update Document |
| GET | `/api/documents/{doc_id}/chunks` | Get Chunks |
| GET | `/api/documents/{doc_id}/download` | Download |
| POST | `/api/documents/{doc_id}/reindex` | Reindex |
| POST | `/api/documents/{doc_id}/versions` | New Version |

### notifications

| Method | Path | Summary |
|---|---|---|
| GET | `/api/notifications` | List Notifications |
| GET | `/api/notifications/preferences` | Prefs |
| PUT | `/api/notifications/preferences` | Set Prefs |
| POST | `/api/notifications/read-all` | Mark All |
| POST | `/api/notifications/{nid}/read` | Mark Read |
| POST | `/api/notifications/{nid}/unread` | Mark Unread |

### organisations

| Method | Path | Summary |
|---|---|---|
| POST | `/api/invitations/accept` | Accept Invitation |
| GET | `/api/invitations/lookup` | Lookup Invitation |
| GET | `/api/orgs` | My Orgs |
| POST | `/api/orgs` | Create Org |
| GET | `/api/orgs/current` | Current Org |
| PATCH | `/api/orgs/current` | Update Org |
| GET | `/api/orgs/current/audit-logs` | Audit Logs |
| POST | `/api/orgs/current/delete` | Request Org Deletion |
| POST | `/api/orgs/current/delete/cancel` | Cancel Org Deletion |
| GET | `/api/orgs/current/invitations` | List Invitations |
| POST | `/api/orgs/current/invitations` | Invite |
| DELETE | `/api/orgs/current/invitations/{inv_id}` | Revoke Invitation |
| POST | `/api/orgs/current/leave` | Leave Org |
| GET | `/api/orgs/current/members` | List Members |
| DELETE | `/api/orgs/current/members/{member_id}` | Remove Member |
| PATCH | `/api/orgs/current/members/{member_id}` | Change Role |
| POST | `/api/orgs/current/members/{member_id}/deactivate` | Deactivate Member |
| POST | `/api/orgs/current/members/{member_id}/reactivate` | Reactivate Member |
| GET | `/api/orgs/current/workspaces` | List Workspaces |
| POST | `/api/orgs/current/workspaces` | Create Workspace |
| DELETE | `/api/orgs/current/workspaces/{ws_id}` | Delete Workspace |
| PATCH | `/api/orgs/current/workspaces/{ws_id}` | Update Workspace |

### public

| Method | Path | Summary |
|---|---|---|
| GET | `/api/forms/{token}` | Get Form |
| POST | `/api/forms/{token}` | Submit Form |
| GET | `/api/hooks/oauth/{provider}` | Oauth Callback |
| POST | `/api/hooks/stripe` | Stripe Webhook |
| POST | `/api/hooks/workflows/{token}` | Workflow Webhook |

### support

| Method | Path | Summary |
|---|---|---|
| GET | `/api/support/flags` | My Flags |
| GET | `/api/support/tickets` | My Tickets |
| POST | `/api/support/tickets` | Create Ticket |

### system

| Method | Path | Summary |
|---|---|---|
| GET | `/api/health` | Health |

### tasks

| Method | Path | Summary |
|---|---|---|
| GET | `/api/tasks` | List Tasks |
| POST | `/api/tasks` | Create |
| POST | `/api/tasks/ai/extract` | Ai Extract |
| POST | `/api/tasks/ai/summary` | Ai Summary |
| GET | `/api/tasks/summary` | Summary |
| DELETE | `/api/tasks/{task_id}` | Delete |
| GET | `/api/tasks/{task_id}` | Get |
| PATCH | `/api/tasks/{task_id}` | Update |
| POST | `/api/tasks/{task_id}/attachments` | Attach |
| GET | `/api/tasks/{task_id}/attachments/{att_id}` | Download Attachment |
| POST | `/api/tasks/{task_id}/comments` | Comment |

### workflows

| Method | Path | Summary |
|---|---|---|
| GET | `/api/workflows` | List Workflows |
| POST | `/api/workflows` | Create Workflow |
| GET | `/api/workflows/executions/{ex_id}` | Execution |
| POST | `/api/workflows/executions/{ex_id}/cancel` | Cancel |
| POST | `/api/workflows/executions/{ex_id}/retry` | Retry |
| POST | `/api/workflows/from-template/{key}` | From Template |
| GET | `/api/workflows/nodes` | Nodes |
| GET | `/api/workflows/templates` | Templates |
| DELETE | `/api/workflows/{wf_id}` | Archive |
| GET | `/api/workflows/{wf_id}` | Get Workflow |
| PUT | `/api/workflows/{wf_id}` | Update Workflow |
| GET | `/api/workflows/{wf_id}/analytics` | Analytics |
| GET | `/api/workflows/{wf_id}/executions` | Executions |
| POST | `/api/workflows/{wf_id}/pause` | Pause |
| POST | `/api/workflows/{wf_id}/publish` | Publish Ep |
| POST | `/api/workflows/{wf_id}/run` | Run |
| POST | `/api/workflows/{wf_id}/validate` | Validate |
| POST | `/api/workflows/{wf_id}/versions/{version}/restore` | Restore |
