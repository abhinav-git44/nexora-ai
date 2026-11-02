# Analytics Framework

## 1. North Star Metric
**Weekly Successful AI-Assisted Business Outcomes (WSAO).**

An *outcome* is a completed, user-valuable action where AI did material work **and** the result was accepted or used. Implemented
as the `outcome_achieved` event (`app/core/audit.py::outcome`) emitted only at these points:

| outcome_type | Emitted when | Why it counts |
|---|---|---|
| `knowledge_answer` | Standalone KB ask returns ≥1 citation | Grounded answer delivered |
| `document_summarised` | Summary generated on request | Reading time saved |
| `data_extracted` | Structured extraction returned valid schema JSON | Re-keying avoided |
| `report_generated` | Report mode / dataset report completed | Hours of assembly avoided |
| `data_question_answered` | NL→SQL query **succeeded** (validated & executed) | Analyst request avoided |
| `tasks_created_from_notes` | User **confirmed** AI-suggested tasks (create=true) | Follow-ups captured |
| `task_completed` | Task moved to done (flag `ai_generated`) | Work finished |
| `agent_run_completed` | Agent run **succeeded** (incl. after approval) | Multi-step job done |
| `workflow_completed` | Workflow execution **succeeded** | Process ran end-to-end |

**Explicitly excluded:** raw AI responses, failed/refused calls, cache hits by themselves, demo seed actions in external reporting.
*Known limitation:* chat answers in conversations are counted as `ai_query_completed` (engagement), not outcomes, until we add an
"answer was useful" signal beyond 👍 feedback.

## 2. Metric tree
```
WSAO ─┬─ Active orgs (weekly) × outcomes per active org
      │        ├─ Activation: time to first value, % orgs with outcome in week 1
      │        └─ Retention: D7/D30/D90 user & org retention
      └─ Quality guardrails: answer correctness, groundedness, hallucination rate, workflow success
         Cost guardrail: AI cost per outcome
```

## 3. KPI catalogue
| Stage | KPI | Definition | Where |
|---|---|---|---|
| Acquisition | Website visits | GA4 page_view on marketing site | Google Analytics (planned tag) |
| | Sign-up conversion | `user_signed_up` ÷ landing visitors | GA4 + Mixpanel |
| | CAC | Acquisition spend ÷ new paying orgs | Finance + model |
| Activation | Time to first value | min(`outcome_achieved`) − `user_signed_up` (median) | `analytics.activation_funnel` |
| | First doc / AI / workflow | Share of signups with each first event | same |
| Engagement | WAU | distinct users with any event / week | `analytics.feature_adoption_weekly` |
| | AI interactions | `ai_query_completed` | dashboard |
| | Workflow executions | `workflow_executed` | dashboard |
| | Feature adoption | users of module ÷ active users | dashboard |
| Retention | D7/D30/D90 | active in day window 7–13 / 30–36 / 90–96 after signup | `analytics.retention_cohorts` |
| | Org retention | orgs with ≥1 outcome in month N+1 ÷ month N | SQL |
| Revenue | MRR / ARR | Σ active subscription prices | `analytics.mrr_by_plan` (demo flagged) |
| | Free→paid | orgs upgrading ÷ trial cohort | billing events |
| | ARPA, expansion, churn | standard definitions | finance |
| AI quality | Correctness, groundedness, citation accuracy, hallucination | eval runner | `ai-engine/results` |
| | AI failure rate, latency | `ai_requests.status`, `latency_ms` | `analytics.ai_usage_daily` |
| | Cost per outcome | AI cost ÷ outcomes | `analytics.cost_per_outcome_weekly`, dashboard |
| Operations | Workflow success, avg execution time | executions | `analytics.workflow_reliability_daily` |
| | Uptime | external probe of `/api/health` | status page (planned) |
| | Support resolution time | ticket resolved − created | admin |

## 4. Event taxonomy (Mixpanel-compatible)
Naming: `object_action` snake_case, past tense. Common properties: `org_id` (Mixpanel group key), `distinct_id` = user id,
`$insert_id` for de-duplication. Defined in `app/core/audit.py::EVENTS` (unknown names log a warning).

| Event | Key properties |
|---|---|
| user_signed_up | via_invite, method |
| user_logged_in, email_verified | — |
| org_created, workspace_created | default |
| member_invited, invitation_accepted | role |
| onboarding_completed | — |
| document_uploaded | file_type, size_kb |
| document_indexed / document_index_failed | chunks, injection_flags / error |
| ai_query_submitted / ai_query_completed / ai_query_failed | mode, knowledge / model, citations, latency_ms, demo |
| agent_created, agent_executed, agent_run_succeeded, agent_run_failed | template, tools, steps, tokens |
| workflow_created, workflow_published, workflow_executed, workflow_completed, workflow_failed | version, trigger, nodes, duration_ms |
| dataset_uploaded, dataset_queried | rows, columns, status |
| task_created, task_completed, tasks_extracted_by_ai | source, count |
| subscription_started, subscription_upgraded, subscription_downgraded, subscription_canceled | from, to, mode |
| integration_connected, integration_disconnected | provider |
| approval_decided | decision, source |
| conversation_shared, response_exported, report_generated | format, source |
| experiment_exposed | experiment, variant |
| outcome_achieved | outcome_type (+ context) |

Delivery: events are written to `analytics_events` (source of truth, SQL/Power BI) and, when `MIXPANEL_TOKEN` is set, forwarded by
the worker (`mixpanel_forward` job) — so analytics never block user requests.

## 5. "Time saved" — documented estimate methodology
`time_saved_hours = Σ_outcome_type (count × assumed manual minutes) ÷ 60` with assumptions in `app/modules/analytics.py`:
knowledge_answer 6 · document_summarised 10 · data_extracted 8 · report_generated 45 · agent_run_completed 15 ·
workflow_completed 5 · tasks_created_from_notes 3 · data_question_answered 12 · task_completed 0.
The UI always shows this with an **Estimate** badge. Validation plan: time-and-motion sampling with design partners (baseline vs
assisted) before any external claim.

## 6. Dashboards
* **In-product executive dashboard** (`/app/analytics`): KPIs with previous-period deltas, daily/weekly/monthly trends,
  drill-downs (cost by model/feature/user), feature adoption, outcome mix, CSV export.
* **Admin product metrics** (`/admin` → Product metrics): signups, activation, D7/D30, NSM weekly, experiments.
* **Power BI**: connect to `analytics.*` views with the read-only role (DEPLOYMENT_GUIDE §Power BI).
