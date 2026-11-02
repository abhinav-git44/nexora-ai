# Financial Model

Workbook: [`business/NEXORA_Financial_Model.xlsx`](business/NEXORA_Financial_Model.xlsx) — formula-driven, 36 months, three scenarios
(select in `Assumptions!B2`). Regenerate with `scripts/build_financial_model.py`; values below were recalculated with LibreOffice.

> **Everything is hypothetical.** There are no customers, revenue or production costs. *Actual* costs to date are limited to
> development tooling and are not modelled. All inputs are labelled assumptions with sources/notes in the Assumptions sheet.

## 1. Key assumptions (Base)
| Driver | Base | Conservative | Optimistic |
|---|---|---|---|
| Signups month 1 / MoM growth (Y1; halves in Y2, halves again in Y3) | 120 / 10% | 80 / 6% | 200 / 14% |
| Trial → paid conversion | 6% | 4% | 9% |
| New paid mix Starter / Pro / Ent | 65 / 32 / 3% | 70 / 28 / 2% | 58 / 37 / 5% |
| Monthly churn Starter / Pro / Ent | 4 / 2.5 / 1% | 5 / 3.5 / 1.5% | 3 / 2 / 0.8% |
| CAC self-serve / Enterprise | $550 / $5,000 | $800 / $7,000 | $350 / $4,000 |
| Blended AI cost per message / per agent run | $0.009 / $0.04 | $0.015 / $0.06 | $0.006 / $0.03 |
| Team cost / month (Y1 / Y2 / Y3) | $18k / $35k / $55k | $20k / $38k / $60k | $18k / $40k / $70k |
| Starting cash | $250k | $250k | $250k |

**AI cost per message derivation (Base):** routing mix ≈ 60% balanced-tier chat (Claude Sonnet 5.5 at $2/$10 per MTok; ~4k input
incl. retrieved context, ~500 output → ~$0.013), 30% fast-tier tasks (Haiku 5.5 at $0.10/$0.50 → <$0.001), 10% frontier analysis
(Opus 5.5 at $4/$20; ~6k in / 1.5k out → ~$0.054); with ~20% prompt-cache savings on stable prefixes ≈ **$0.009**. Prices from
Anthropic's published model table (cached Oct 2026); OpenAI route prices in `ai/catalog.py` are flagged *verify*.

## 2. Scenario outputs
| | Conservative | **Base** | Optimistic |
|---|---|---|---|
| Paying orgs — M12 / M24 / M36 | 44 / 96 / 147 | **133 / 380 / 691** | 445 / 1,626 / 3,488 |
| MRR M36 | $18.9k | **$109.5k** | $779k |
| ARR M36 | $0.23M | **$1.31M** | $9.35M |
| Blended gross margin M36 | 37% | **68%** | 82% |
| Break-even month (net income ≥ 0) | Not within 36 | **Not within 36** (M36 net −$14.7k) | Month 9 |
| Lowest cumulative cash (after $250k start) | −$1.29M | **−$0.67M** | +$0.12M |
| ⇒ Total capital needed (incl. $250k start) | ~$1.55M | **~$0.92M** | ~$0.25M (starting cash suffices) |

## 3. Unit economics (Base)
| | Starter | Pro | Enterprise |
|---|---|---|---|
| Gross margin % | 67% | 63% | 77% |
| LTV/CAC | 1.5× | 9.1× | 23× |
| Payback | 16.8 mo | 4.4 mo | 4.3 mo |
Blended ARPA at M36 ≈ $158/month.

## 4. Sensitivity — AI cost and usage
Professional gross margin (Sensitivity sheet):

| AI $/message ↓ · utilisation of 10k limit → | 15% | 25% | 35% | 50% | 75% | 100% |
|---|---|---|---|---|---|---|
| $0.003 | 83% | 78% | 73% | 66% | 53% | 41% |
| $0.006 | 81% | 74% | 68% | 58% | 42% | 26% |
| **$0.009 (Base)** | 79% | 71% | **63%** | 51% | 31% | 11% |
| $0.012 | 76% | 67% | 57% | 43% | 19% | −4% |
| $0.015 | 74% | 63% | 52% | 36% | 8% | −19% |
| $0.020 | 70% | 57% | 43% | 23% | −11% | −44% |
| $0.030 | 63% | 44% | 26% | −2% | −48% | −95% |

**Interpretation:** profitability is far more sensitive to *heavy users × model choice* than to price. A Pro customer using the full
allowance on a balanced model is barely profitable; on a frontier model they are loss-making. This is why the product meters every
call, routes by task, exposes cost per outcome, and why the pricing recommendation is to cap Pro at 5,000 included messages with paid
credit packs (MONETISATION_STRATEGY §4).

## 5. Break-even analysis
In Base, monthly net income approaches zero by month 36 (−$14.7k) because team cost steps up to $55k/month in year 3. Break-even
needs one of: ~+1.5 pts trial→paid conversion, a Pro-heavier mix (≥40% of new paid), or holding Y3 team cost at ~$40k. The
Optimistic case breaks even in month 9 — treat it as an upper bound, not a plan.

## 6. What would change the model (to validate first)
Trial→paid conversion and Pro mix (design partners + E4/E5), real AI cost per message from production ledgers
(`analytics.ai_usage_daily`), and churn by plan after 3 months of paid usage.
