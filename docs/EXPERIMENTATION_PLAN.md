# Experimentation Plan

> **No experiment has been run with real users. No results are reported.** Assignment infrastructure is implemented
> (`app/modules/experiments.py`: deterministic SHA-256 bucketing, sticky assignments, `experiment_exposed` events; admin results view
> shows assignment counts only).

Standard method: two-sided test, α = 0.05, power = 0.8; sample size n per arm ≈ 16·p(1−p)/δ² (approximation for proportions).
Stop rules: pre-registered duration; no peeking-based early stops except guardrail breaches.

| # | Experiment | Hypothesis | Segment / unit | Control | Variant | Primary metric | Guardrails | Sample size assumption | Duration | Decision rule |
|---|---|---|---|---|---|---|---|---|---|---|
| E1 | `onboarding_flow` | A guided checklist with sample docs increases week-1 activation | New users | Short onboarding (checklist only) | Guided: sample docs pre-loaded + inline tips | % users with ≥1 outcome in 24h | Signup→first session drop-off; support tickets | Baseline 30%, MDE +6 pts → ~950/arm | 3–4 weeks | Ship if lift ≥ MDE and guardrails flat |
| E2 | `assistant_starter_prompts` | Role-based starter prompts increase first-session questions | New users | No prompts | 4 role-tailored prompts | % users with `ai_query_completed` in session 1 | Answer 👎 rate | Baseline 45%, MDE +7 pts → ~800/arm | 2–3 weeks | Ship if lift and 👎 rate not worse by >2 pts |
| E3 | `kb_upload_experience` | Offering sample documents raises upload completion | New orgs | Empty dropzone | Dropzone + "Try with sample policies" | `document_indexed` within 24h | Share of orgs uploading *own* docs by day 7 | Baseline 40%, MDE +8 pts → ~600/arm | 3 weeks | Ship only if own-doc uploads don't fall |
| E4 | `free_tier_limits` | A higher free limit increases activation without hurting conversion | New orgs (post-trial) | 150 msgs/mo | 300 msgs/mo | Free→paid conversion at 30d | AI cost per free org; activation | Baseline 6%, MDE ±2 pts → ~2,300/arm | 6–8 weeks | Keep 150 unless conversion ≥ control and cost acceptable |
| E5 | `pricing_page` | Showing annual billing by default increases plan starts | Visitors | Monthly default | Annual default (2 months free) | `subscription_started` per pricing view | Refund requests; checkout abandonment | Baseline 3%, MDE +1 pt → ~4,600/arm | 6 weeks | Ship if lift significant and refunds flat |
| E6 | `ai_workflow_suggestions` | Suggesting a workflow after repeated manual actions increases publishing | Orgs with ≥3 repeated actions | No suggestion | In-context suggestion card | `workflow_published` within 7d | Notification opt-outs; workflow failure rate | Baseline 10%, MDE +5 pts → ~600/arm | 4 weeks | Build only if lift ≥5 pts (feature flag `ai_workflow_suggestions`) |

**Simulations:** none presented. If a simulation is added (e.g. power curves), it will be labelled "Simulation — synthetic data".

**Analysis SQL:** `analytics.experiment_exposure` joins assignments to outcomes; per-experiment notebooks to be added when traffic exists.
