# Market Research (desk research)

> **Method & honesty statement.** This is secondary (desk) research using public sources, accessed **November 2026**, plus clearly
> labelled hypotheses. **No customer interviews, surveys or usability studies have been conducted.** Where sources disagree, ranges are
> given and the item is marked *verify*. A validation plan for each hypothesis is in §6.

## 1. Market context
| Signal | Data point | Source |
|---|---|---|
| AI adoption is mainstream but shallow | McKinsey's 2025 global survey reports **88%** of respondents say their organisation uses AI in at least one function (up ~10 pts on 2024), while most are not yet scaling it | [McKinsey — "AI at work but not at scale"](https://www.mckinsey.com/featured-insights/week-in-charts/ai-at-work-but-not-at-scale) |
| India's SMB base is large and digitising | **~7.3 crore** enterprises registered on Udyam/UAP by Dec 2025 (5.89 crore in Jan 2025) | [The Statesman (MSME Ministry year-end review)](https://www.thestatesman.com/business/msme-sector-achieves-key-milestones-in-2025-udyam-registrations-cross-7-3-crore-msme-ministry-1503532923.html); [KNN India](https://knnindia.co.in/news/newsdetails/msme/over-728-cr-msmes-registered-on-udyam-portal-since-2020-mos) |
| US SMB base | ~6.4M **employer** small businesses and ~30M non-employer firms (secondary citation of SBA Advocacy; *verify* against SBA profile) | [review42 (citing SBA)](https://resources.review42.com/small-business-statistics/); [SBA Advocacy 2025 profile](https://advocacy.sba.gov/wp-content/uploads/2025/06/United_States_2025-State-Profile.pdf) |
| AI is being bundled into productivity suites | Notion bundles full AI into Business (~$20/user/mo annual, sources vary); Microsoft 365 Copilot Business ~$21/user/mo list with promotional pricing reported | [userjot — Notion pricing](https://userjot.com/blog/notion-pricing-2025-plans-ai-costs-explained); [Microsoft Tech Community](https://techcommunity.microsoft.com/t5/microsoft-365-copilot-blog/act-now-lock-in-current-pricing-on-microsoft-365-copilot/ba-p/4502628) |
| Automation tools price by tasks/executions | Zapier Team reported $69–$103.50/mo (sources disagree); n8n Cloud Starter ~$24/mo, self-host free | [toolradar — Zapier](https://toolradar.com/blog/zapier-pricing-2026); [costbench — n8n vs Zapier](https://www.costbench.com/compare/n8n-vs-zapier/) |

**Implication:** buyers already pay per-seat for AI inside suites and per-task for automation. A small team that wants *both* plus
governance stacks 2–4 subscriptions. NEXORA prices per **organisation** (seat bands) to undercut stacked per-seat AI costs for 5–20
person teams — see MONETISATION_STRATEGY.md.

## 2. Market sizing (TAM / SAM / SOM)
All figures are **order-of-magnitude assumptions** (also in the financial model, sheet *Market sizing*).

| Layer | Definition | Orgs | Value / org / yr | Size | Basis |
|---|---|---|---|---|---|
| TAM | Global SMB & mid-market (10–500 staff) using cloud productivity tools | ~9M | $2,400 | **~$21.6B** | Hypothesis anchored on US employer-firm + India MSME counts, filtered to digital, 10+ staff |
| SAM | English-first digital SMBs (India, US, UK, SEA), 10–200 staff, ops/knowledge pain, self-serve buyers | ~1.2M | $1,800 | **~$2.2B** | Assumed ~13% of TAM reachable through PLG + content |
| SOM (36 mo, Base) | Realistic capture for a seed-stage PLG company | ~690 | ~$1,900 | **~$1.3M ARR** | Output of the Base scenario |

The SOM is deliberately small: the strategic point is that a **capital-efficient niche** (ops-heavy 10–200 person teams) is enough to
reach ~$1.3M ARR in Base and to learn whether the governance/measurement wedge supports expansion.

## 3. Customer workflows observed in public material (hypotheses)
1. **Policy & process Q&A** — HR/finance/IT FAQs answered repeatedly by the same person.
2. **Meeting → follow-ups** — action items captured in notes but not converted into owned tasks.
3. **Recurring reporting** — weekly status/ops reports assembled by hand from exports.
4. **Intake & routing** — forms/emails/leads triaged manually, often in spreadsheets.
5. **Ad-hoc data questions** — "top customers this quarter" waits for an analyst.

## 4. Pain points & adoption barriers
| Pain point (H = hypothesis) | Evidence type |
|---|---|
| H1 Ops leads are interrupted many times/day with "where is / how do we" questions | Public practitioner content; *to validate in interviews* |
| H2 Generic AI chat isn't trusted for company-specific answers because it can't cite internal sources | Common objection in AI-adoption commentary; *validate* |
| H3 SMB automations break silently and nobody owns them | Practitioner content on no-code automation maintenance; *validate* |
| H4 Leaders can't quantify AI ROI, so budgets stall | Consistent with "adopted but not scaled" findings (McKinsey 2025) |

| Barrier | Mitigation in product |
|---|---|
| Data-security fear ("will it leak to other customers / train models?") | Tenant isolation tests, BYOK option, no training on customer data stated in policy, DPDP-aligned controls |
| Setup effort | Templates for agents/workflows, sample documents, 15-minute onboarding checklist |
| Cost unpredictability | Hard plan limits (no overage), cost dashboard, cost per outcome |
| Accuracy anxiety | Citations with verification flags, "not found" behaviour, evaluation framework |

## 5. Willingness-to-pay hypotheses
* WTP-1: A 10-person team already paying ~$20/seat/month for AI inside a suite (~$200/mo) will consider **$199/mo for the whole
  team** if it adds governance + workflows. *Test:* pricing-page experiment (EXPERIMENTATION_PLAN E5) + design-partner interviews.
* WTP-2: Teams of 3–5 are price-sensitive below $50/month. *Test:* Starter conversion vs. Free limit experiment (E4).
* WTP-3: Indian SMBs expect INR pricing with GST invoices and UPI/cards. *Test:* checkout funnel split by currency once Razorpay ships.

## 6. Validation plan (next 6 weeks — not yet executed)
| Week | Activity | Output | Decision it informs |
|---|---|---|---|
| 1–2 | 12–15 problem interviews (ops leads, HR managers, founders) using a structured script | Pain frequency & severity scores | Confirm/reject H1–H4 |
| 2–3 | 5 design partners onboarded on real documents (with DPA) | Private eval sets; time-to-first-value | Activation wedge |
| 3–4 | Van Westendorp price survey to design partners + waitlist | Acceptable price range | Starter/Pro pricing |
| 4–6 | Fake-door tests for connectors (Google Drive, Slack, Jira) | Click-through by connector | Integration roadmap order |
