# Product Roadmap

Dates are relative to the start of the build (Month 0 = this repository's V1). Everything after "MVP" is a plan, not a commitment.

## Overview
| Release | Window | Theme | Key outcomes |
|---|---|---|---|
| **MVP (built)** | M0 | Governed knowledge + first automations | Cited answers, notes→tasks, agents with approvals, workflows, safe data Q&A, billing, admin |
| **V1** | M1–M3 | Design partners & India launch | Monitoring, streaming, RLS, Razorpay, Slack, credit packs, private evals, Drive sync |
| **V2** | M4–M8 | Connected operations | Jira/Confluence/HubSpot sync, scheduled agents, multi-table data, SSO, ROI report |
| **Future** | M9+ | Operations intelligence | Proactive bottleneck detection, AI-suggested workflows, vertical packs, regional data residency |

## MVP — delivered (Sprint 1–6 equivalent)
| Sprint | Scope | Exit evidence |
|---|---|---|
| S1 | Auth, orgs, RBAC, invitations | `test_auth.py`, `test_tenancy_rbac.py` |
| S2 | AI gateway, ingestion, hybrid RAG, assistant, job queue | `test_knowledge_rag.py`, `test_assistant.py` |
| S3 | Agent runtime, templates, approvals | `test_agents.py` |
| S4 | Workflow engine & builder | `test_workflows.py`, E2E #5 |
| S5 | Data intelligence, tasks, notifications | `test_data.py`, `test_tasks_billing.py` |
| S6 | Billing, integrations, analytics, admin, evals, deployment | Newman, eval report, compose E2E |

## V1 (M1–M3) — "Design partners & India launch"
| Item | Why now | Depends on | Risk |
|---|---|---|---|
| Sentry + OpenTelemetry | Real data needs real observability | — | Low |
| Streaming responses | Real-LLM latency (8–20s) feels slow without streaming | Gateway | Low |
| Postgres RLS | Defence in depth before scale | Tenancy model | Medium (policy bugs) |
| Razorpay + GST invoices | India-first pricing | Billing | Medium (compliance) |
| AI credit packs + Pro cap 5,000 msgs | Margin protection (FINANCIAL_MODEL §4) | Metering | Pricing perception |
| Slack alerts | Approvals where people already are | Integrations | Low |
| Private eval sets per partner | Prove quality on *their* docs | Eval framework | Data handling (DPA) |
| Google Drive sync | Most-requested source (hypothesis) | Interviews | OAuth verification time |

**V1 milestones:** M1 — 5 design partners onboarded with DPAs. M2 — India public beta (INR). M3 — paid conversion of ≥10 orgs.

## V2 (M4–M8) — "Connected operations"
Jira/Confluence/HubSpot two-way sync · scheduled & event-triggered agents · multi-table datasets with allow-listed joins ·
SAML SSO + SCIM (Enterprise) · customer-facing ROI report with validated time-saved method · workflow templates marketplace ·
cross-encoder reranker if evals justify.

## Future innovation (M9+)
* **Operations radar:** detect stuck tasks, SLA drift, repeated questions (→ suggest a doc), cost anomalies.
* **AI-suggested workflows** from observed repetitive actions (experiment E6 first).
* **Vertical packs:** HR ops, agency ops, SaaS customer success — templates + evals.
* **Regional data residency** (India region first) and customer-managed keys.

## Risk register
| Risk | Prob. | Impact | Mitigation | Owner |
|---|---|---|---|---|
| AI answers wrong on customer docs | Med | High | Citations, "not found", private evals, feedback loop | Product/AI |
| Cross-tenant leakage | Low | Critical | Org-scoped queries, tests, RLS (V1), pen-test | Eng |
| Gross margin erosion from heavy users | Med | High | Routing, caching, plan caps, credit packs, cost alerts | Product/Finance |
| Provider outage | Med | Med | Multi-provider fallback, demo engine degrade, status page | Eng |
| Suites bundle similar features | High | High | Focus on governance + outcomes + India; integrate with suites | Product |
| Slow sales cycles for Enterprise | High | Med | PLG first; Enterprise only for inbound | GTM |
| DPDP compliance gaps | Med | High | Privacy review, consent notices, data maps, DPO process | Legal/Product |
