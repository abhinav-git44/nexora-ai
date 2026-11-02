# Product Strategy

## 1. Where we play
**Primary segment:** digital-first SMBs and lower mid-market companies (10–200 employees) — startups, SaaS/tech companies and
service businesses — in **India first, then English-speaking markets**, where an *operations owner* (COO, Ops Manager, Chief of
Staff, founder) is accountable for processes but has no dedicated knowledge-management or automation team.

**Secondary:** HR, sales, customer support and consulting teams inside the same companies (expansion seats), and consultants who run
operations for several small clients (multi-organisation users).

**Explicitly not now:** large enterprises with mandatory on-prem/SSO-only procurement (Enterprise tier is "contact sales" and
deliberately thin in V1), regulated healthcare data, and consumer use.

## 2. The problem we solve (jobs-to-be-done)
| Job | Today's workaround | Pain |
|---|---|---|
| "When a teammate asks how we do X, give them the *right, current* answer without pinging me." | Slack DMs to the ops lead; wiki search | Interruptions, stale answers, single point of failure |
| "Turn this meeting into owned, dated follow-ups." | Someone types notes into a task tool after the meeting | Action items lost; no owner |
| "Answer a numbers question from our export without waiting for an analyst." | Pivot tables; ad-hoc requests to the one SQL person | Days of latency; errors |
| "Make the recurring hand-off happen automatically, but let me approve the risky step." | Zapier zaps nobody owns, manual checklists | Brittle automations, no audit trail, no approvals |
| "Show leadership whether AI is actually saving time and what it costs." | Anecdotes | No measurement; budget scepticism |

## 3. Value proposition
For operations-heavy small and mid-sized teams who lose hours to searching, chasing and re-keying, **NEXORA** is an AI operations
workspace that **answers questions from your own documents with sources, turns conversations into owned tasks, runs approval-gated
workflows and answers data questions safely** — unlike general chat assistants (ungrounded, ungoverned) or automation tools (no
knowledge, no AI governance), NEXORA combines them under **one permission model, one audit trail and one cost dashboard.**

## 4. Positioning & differentiation
* **Category:** AI business operations workspace (between knowledge assistants like Notion AI/Glean and automation like Zapier/n8n).
* **Differentiators (defensible order):**
  1. *Governance built in for SMB budgets* — role-aware retrieval, tool allow-lists, approvals and audit logs on mid-tier plans,
     which competitors typically reserve for enterprise contracts.
  2. *Outcome & cost transparency* — North Star "AI-assisted outcomes" and **cost per outcome** visible to the customer.
  3. *Workflow + agent + knowledge in one data model* — a document upload can trigger a workflow that summarises it, routes an
     approval and creates tasks; no glue code.
  4. *India-ready* — INR pricing, DPDP-aligned data handling, Razorpay billing path (planned).
* **What we will not compete on:** breadth of connectors (n8n/Zapier win; we integrate n8n instead), raw model quality (we route to
  the best available provider), enterprise search across 100+ SaaS sources (Glean's home turf).

## 5. Strategic bets & how we'll know
| Bet | Signal that it's right | Kill/pivot signal |
|---|---|---|
| Grounded Q&A is the activation wedge | ≥40% of new orgs reach a cited answer in session 1; D7 retention of those users ≥ 25% | Users upload docs but don't return to ask |
| Approvals unlock automation adoption | Workflows with an approval node have higher publish→run continuation | Approvals are bypassed or seen as friction |
| Ops leaders pay for governance + measurement | Pro conversions cite audit logs / analytics in exit survey | Conversions only for higher message limits (→ we're a chat reseller) |
| Usage-based margin is controllable | Blended AI cost/message ≤ $0.009 at Base utilisation | Gross margin < 60% for two consecutive months |

## 6. Business model summary
Freemium + 14-day reverse trial of Professional → Free, Starter ($49/mo, 5 seats), Professional ($199/mo, 20 seats), Enterprise
(custom). Usage limits block rather than overcharge. Financial model findings drive two pricing changes proposed for V1 (see
MONETISATION_STRATEGY.md §5): cap Pro AI messages at 5,000 with credit packs, and acquire Starter only through low-CAC channels.

## 7. OKRs — first two quarters after launch (targets are hypotheses to validate)
**O1. Prove the activation wedge.** KR1: median time-to-first-cited-answer < 10 minutes. KR2: 40% of new orgs achieve ≥1 AI-assisted
outcome in week 1. KR3: answer-correctness ≥ 85% on each design partner's private eval set.
**O2. Earn the right to charge.** KR1: 10 design partners on paid plans. KR2: trial→paid ≥ 6%. KR3: gross margin ≥ 65%.
**O3. Make reliability visible.** KR1: workflow success rate ≥ 97%. KR2: p95 assistant latency < 8s with a real LLM. KR3: zero
cross-tenant incidents (continuous tests + pen-test).
