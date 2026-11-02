# Monetisation Strategy

## 1. Pricing model
**Per-organisation plans with seat bands + hard usage limits** (implemented in `backend/app/core/plans.py`).

| Plan | USD / mo | INR / mo | Members | AI messages / mo | Docs | Agents · Workflows | Key features |
|---|---|---|---|---|---|---|---|
| Free | 0 | 0 | 2 | 150 | 10 | 1 · 1 | Assistant, knowledge, tasks, basic analytics |
| Starter | 49 | 3,999 | 5 | 2,000 | 200 | 5 · 10 | + agents, workflows, team |
| Professional | 199 | 15,999 | 20 | 10,000 | 2,000 | 25 · 100 | + advanced agents/nodes, data intelligence, audit logs, team admin |
| Enterprise | Custom | Custom | Custom | Custom | Custom | Custom | + custom limits, SSO (V2), audit export, priority support |

**Why per-org, not per-seat:** our buyer is the ops owner of a 5–20 person team. Per-seat AI from suites already costs ~$20/user
(COMPETITIVE_ANALYSIS §3); a team price makes adding the HR manager or a sales lead free, which drives expansion *usage* (and outcomes)
rather than seat negotiation. Seat bands protect against a 200-person org on a $199 plan.

**Why hard limits, no overage:** cost unpredictability is an adoption barrier for SMBs. Limits return HTTP 402 with an upgrade path.

**Reverse trial:** every new workspace gets 14 days of Professional, then falls back to Free automatically (lazy evaluation, no cron
dependency). Rationale: users experience data intelligence and governance before deciding.

**INR pricing:** set at ~80% of USD at market exchange rates to reflect local willingness to pay (hypothesis WTP-3).

## 2. Value metric
Primary: **AI-assisted outcomes** (what customers value). Billed proxy: AI messages + agent runs + workflow runs (what drives our
cost). We report both to the customer so the price feels tied to value, not tokens.

## 3. Unit economics (Base scenario, from the financial model)
| | Starter | Professional | Enterprise |
|---|---|---|---|
| Price / mo | $49 | $199 | $1,500 (avg) |
| AI cost / mo (35% utilisation) | $8.70 | $55.50 | $235 |
| Gross margin % | 67% | 63% | 77% |
| CAC | $550 (self-serve) | $550 | $5,000 (sales-led) |
| LTV (GM basis) / CAC | **1.5×** | **9.1×** | 23× |
| CAC payback | 16.8 mo | 4.4 mo | 4.3 mo |

## 4. Findings from the model (decisions)
1. **Starter cannot be bought with paid acquisition** (LTV/CAC 1.5×, 17-month payback). → Starter is acquired only through
   organic/PLG channels (content, templates, referrals, reverse-trial fallback); paid budget targets Pro-fit companies (10–50 staff).
2. **Professional margin collapses with heavy usage**: at $0.009 per message, Pro gross margin is 63% at 35% utilisation of the
   10,000-message limit, 51% at 50%, 31% at 75% and 11% at 100% (Sensitivity sheet). Plan limits are a promise of *maximum* cost.
   → **Proposed V1 change:** Pro includes **5,000** messages + **AI credit packs** (2,500 messages for $50, ~55% margin at Base cost)
   and an alert at 80% usage. Requires experiment E4-style validation before rollout to existing customers (grandfather them).
3. **AI cost per message is the most sensitive driver** — moving from $0.009 to $0.006 lifts Pro margin ~5 pts at Base utilisation.
   → Keep cheap-model routing for summaries/classification, prompt caching on stable system prompts, response caching for idempotent
   tasks, and track `cost_per_outcome` weekly.

## 5. Billing implementation
* **Stripe** (implemented adapter): Checkout for upgrades, Customer Portal for card management, signed webhooks
  (`checkout.session.completed`, `customer.subscription.*`, `invoice.*`) update subscription and invoices. **No card data touches
  NEXORA servers.**
* **India:** Stripe India supports INR but has onboarding constraints for some business types; **Razorpay** (cards, UPI, netbanking,
  GST invoicing, subscriptions API) is the recommended primary provider for INR customers — adapter planned in V1 behind the same
  interface (`RAZORPAY_KEY_ID/SECRET` reserved in `.env.example`). GST: 18% on SaaS (verify with a tax adviser); invoices must carry GSTIN.
* **Demo mode:** with no provider keys, plan changes apply immediately and create invoices marked `demo` with "no payment taken",
  clearly bannered in the UI.

## 6. Expansion levers
Seat-band upgrades (Starter→Pro at 6th member), data intelligence and audit logs (Pro-only), credit packs, Enterprise for SSO/custom
limits, add-on vertical packs (future).
