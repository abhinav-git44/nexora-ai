"""Builds docs/business/NEXORA_Executive_Review.pptx (16:9) from repository facts. Run with the backend venv (python-pptx)."""
from pathlib import Path
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"
BRAND, INK, MUTED, LINE, SOFT = RGBColor(0x5B, 0x5B, 0xD6), RGBColor(0x18, 0x18, 0x1B), RGBColor(0x52, 0x52, 0x5B), RGBColor(0xE4, 0xE4, 0xE7), RGBColor(0xEE, 0xF0, 0xFF)
WARN = RGBColor(0xB4, 0x53, 0x09)
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def text(slide, x, y, w, h, s, size=16, bold=False, color=INK, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    lines = s if isinstance(s, list) else [s]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text, p.alignment = line, align
        p.font.size, p.font.bold, p.font.color.rgb, p.font.name = Pt(size), bold, color, "Calibri"
        p.space_after = Pt(6)
    return tb


def bullets(slide, x, y, w, h, items, size=16):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = "• " + it
        p.font.size, p.font.color.rgb, p.font.name = Pt(size), INK, "Calibri"
        p.space_after = Pt(8)


def base(title, kicker=None, note=None):
    s = prs.slides.add_slide(BLANK)
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.12))
    bar.fill.solid(); bar.fill.fore_color.rgb = BRAND; bar.line.fill.background()
    if kicker:
        text(s, 0.6, 0.35, 12, 0.4, kicker.upper(), 12, True, BRAND)
    text(s, 0.6, 0.65, 12, 0.9, title, 30, True)
    text(s, 0.6, 7.0, 9, 0.3, "NEXORA AI · Executive product review · pre-launch prototype — figures are hypotheses unless marked measured", 9, color=MUTED)
    if note:
        s.notes_slide.notes_text_frame.text = note
    return s


def table(slide, x, y, w, rows, col_w=None, size=12, h=0.38):
    shp = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(h * len(rows)))
    t = shp.table
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            cell = t.cell(r, c)
            cell.text = str(v)
            para = cell.text_frame.paragraphs[0]
            para.font.size, para.font.name = Pt(size), "Calibri"
            para.font.bold = r == 0
            para.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF) if r == 0 else INK
            cell.fill.solid()
            cell.fill.fore_color.rgb = BRAND if r == 0 else (SOFT if r % 2 == 0 else RGBColor(0xFF, 0xFF, 0xFF))
    if col_w:
        for i, cw in enumerate(col_w):
            t.columns[i].width = Inches(cw)
    return t


def pic(slide, name, x, y, w):
    p = SHOTS / name
    if p.exists():
        pc = slide.shapes.add_picture(str(p), Inches(x), Inches(y), width=Inches(w))
        pc.line.color.rgb = LINE


# 1 Title
s = prs.slides.add_slide(BLANK)
bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
bg.fill.solid(); bg.fill.fore_color.rgb = RGBColor(0x13, 0x13, 0x18); bg.line.fill.background()
text(s, 0.8, 2.2, 11, 1, "NEXORA AI", 54, True, RGBColor(0xFF, 0xFF, 0xFF))
text(s, 0.8, 3.3, 11, 0.8, "One intelligent workspace. Infinite business possibilities.", 24, color=RGBColor(0xA9, 0xA9, 0xFF))
text(s, 0.8, 4.3, 11, 1, ["Executive product review — V1 build", "AI business operations & workflow intelligence SaaS · independent product · Nov 2026"], 16, color=RGBColor(0xD4, 0xD4, 0xD8))

# 2 Exec summary
s = base("Executive summary", "Where we are")
bullets(s, 0.6, 1.7, 6.3, 5, [
    "Problem: ops-heavy 10–200 person teams lose hours to repeated questions, lost follow-ups and manual reporting; generic AI is ungrounded and ungoverned.",
    "Product: cited answers from company documents, notes→owned tasks, approval-gated agents & workflows, safe NL→SQL, outcome & cost analytics.",
    "Status: V1 feature-complete and verified (90 backend tests, 8 E2E journeys incl. Docker prod stack, AI eval harness). Not yet launched.",
    "Key decision: model shows Pro margin falls from 63% → 11% at full usage → cap included usage + credit packs before launch.",
    "Ask: 5 design partners with real documents; LLM budget for real-provider evals; ~$0.9M to reach ~break-even (Base case).",
], 15)
pic(s, "10-home.png", 7.2, 1.7, 5.6)

# 3 Problem & opportunity
s = base("Problem & opportunity", "Why now")
table(s, 0.6, 1.7, 6.4, [["Job to be done", "Today"], ["Give the right, current answer without pinging the ops lead", "Slack DMs, stale wiki"],
                         ["Turn meetings into owned follow-ups", "Manual retyping, lost items"], ["Answer a numbers question now", "Wait for analyst"],
                         ["Automate hand-offs, approve risky steps", "Brittle zaps, no audit"], ["Show what AI saves and costs", "Anecdotes"]], [3.6, 2.8], 12)
table(s, 7.4, 1.7, 5.3, [["Signal", "Data"], ["Orgs using AI (McKinsey 2025)", "88%, few at scale"], ["India Udyam-registered MSMEs (Dec 2025)", "~7.3 crore"],
                         ["TAM / SAM (assumption)", "~$21.6B / ~$2.2B"], ["Base SOM @36 mo (model)", "~$1.3M ARR"]], [3.2, 2.1], 12)
text(s, 7.4, 4.3, 5.3, 1.5, "Sources and assumptions: MARKET_RESEARCH.md. No interviews conducted yet — validation plan defined.", 11, color=MUTED)

# 4 Product overview
s = base("Product overview", "What we built")
bullets(s, 0.6, 1.7, 5.2, 5, ["Assistant with verified citations", "Knowledge base: 6 formats, hybrid RAG, role-based access, injection defence",
                              "Agent Studio: 8 templates, tool allow-lists, approvals", "Workflows: 20 nodes, versions, HMAC webhooks, forms, schedules",
                              "Data: NL→SQL with AST guard, charts, exports", "Tasks, analytics, billing, integrations, admin console"], 15)
pic(s, "12-assistant-conversation.png", 6.1, 1.6, 3.4)
pic(s, "18-workflow-builder.png", 9.6, 1.6, 3.4)
pic(s, "20-data-query.png", 6.1, 4.0, 3.4)
pic(s, "16-agent-run.png", 9.6, 4.0, 3.4)

# 5 Key decisions
s = base("Key product decisions", "Trade-offs we made")
table(s, 0.6, 1.7, 12.1, [["Decision", "Instead of", "Why"],
    ["Per-org seat bands, hard limits, no overage", "Per-seat AI pricing", "Cheaper than ~$20/seat suites for 5–20 person teams; predictable bills"],
    ["Provider-neutral AI gateway with task routing", "Single model everywhere", "Cost: cheap models for simple tasks; resilience via fallback"],
    ["Hybrid RAG in Postgres with SQL-level permissions", "Separate vector DB", "Permission filter in the same query; one fewer system"],
    ["Single persisted agent + human approvals", "Multi-agent framework", "Reliability, auditability, pauses across processes"],
    ["Own workflow engine; n8n as a node", "Embed n8n", "We own permissions, approvals, outcomes; n8n gives connectors"],
    ["North Star = weekly AI-assisted outcomes", "AI messages / WAU", "Counts completed value, resists vanity metrics"]], [4.2, 2.7, 5.2], 12)

# 6 Prioritisation
s = base("Feature prioritisation", "RICE · ICE · MoSCoW")
table(s, 0.6, 1.7, 6.2, [["Top MVP stories", "RICE"], ["Signup + password policy", "3000"], ["Role-aware retrieval", "2700"], ["Verified citations", "2430"],
                         ["AI notes → tasks", "1920"], ["Approvals for sensitive tools", "1620"], ["RBAC · chat · plans/limits", "1500"]], [4.7, 1.5], 13)
table(s, 7.2, 1.7, 5.5, [["Next (V1)", "Why"], ["Monitoring & tracing", "Before real data"], ["Streaming responses", "Real-LLM latency"], ["Postgres RLS", "Defence in depth"],
                         ["Razorpay (INR, GST)", "India-first dependency"], ["AI credit packs", "Margin protection"]], [2.8, 2.7], 13)
text(s, 0.6, 5.0, 12, 1.2, "Excluded deliberately: multi-agent orchestration, 100+ connectors (n8n covers), real-time co-editing, native mobile, fine-tuning.", 13, color=MUTED)

# 7 AI architecture
s = base("AI architecture", "Governed by design")
table(s, 0.6, 1.7, 6.6, [["Task", "Primary model", "Why"], ["Classify / summarise", "Claude Haiku 5.5", "Cheap, fast, sufficient"],
                         ["Chat / RAG / agents / extract", "Claude Sonnet 5.5", "Balanced quality & cost"], ["Analysis / reports", "Claude Opus 5.5", "Hard reasoning, low volume"],
                         ["Fallbacks", "OpenAI GPT routes → demo engine", "Resilience"]], [2.2, 2.3, 2.1], 12)
bullets(s, 7.5, 1.7, 5.3, 5, ["Every call metered: tokens, cache, cost, latency, fallback", "Prompt + response caching; token budgets; per-org rate limits",
                              "PII redaction before provider; secret stripping on output", "Injection: detect → neutralise → frame as data → down-rank",
                              "Agents: allow-listed tools, role re-check, approval for side-effects", "NL→SQL: AST allow-list, read-only txn, timeout, row cap"], 14)

# 8 Metrics
s = base("Product metrics", "North Star & guardrails")
bullets(s, 0.6, 1.7, 6.0, 5, ["North Star: weekly successful AI-assisted outcomes — only completed, accepted actions count",
                              "Activation: time to first cited answer < 10 min; week-1 outcome rate",
                              "Quality guardrails: correctness ≥ 85%, hallucination ≤ 5%, workflow success ≥ 97%",
                              "Cost guardrail: AI cost per outcome (customer-visible)",
                              "Time saved shown only as a labelled estimate with published assumptions",
                              "Mixpanel taxonomy + Power BI-ready SQL views"], 14)
pic(s, "22-analytics.png", 6.9, 1.6, 5.9)

# 9 Business case
s = base("Business case (hypothetical 36-month model)", "Scenarios")
table(s, 0.6, 1.7, 12.1, [["", "Conservative", "Base", "Optimistic"], ["Paying orgs (M36)", "147", "691", "3,488"], ["ARR (M36)", "$0.23M", "$1.31M", "$9.35M"],
                          ["Blended gross margin (M36)", "37%", "68%", "82%"], ["Break-even", "> 36 mo", "just > 36 mo", "Month 9"],
                          ["Total capital need", "~$1.55M", "~$0.92M", "~$0.25M"]], [4.1, 2.6, 2.7, 2.7], 14)
text(s, 0.6, 4.4, 12, 1.5, ["Base assumptions: 120 signups in M1, 10% MoM growth decaying, 6% trial→paid, 65/32/3 plan mix, $550 self-serve CAC, $0.009 AI cost/message.",
                            "Unit economics (Base): Pro LTV/CAC 9.1× (4.4-mo payback) · Starter 1.5× → Starter acquired organically only."], 13, color=MUTED)

# 10 Sensitivity chart
s = base("Profitability is most sensitive to heavy usage × model cost", "Sensitivity")
cd = CategoryChartData()
cd.categories = ["15%", "25%", "35%", "50%", "75%", "100%"]
cd.add_series("$0.006 / msg", (81, 74, 68, 58, 42, 26))
cd.add_series("$0.009 / msg (Base)", (79, 71, 63, 51, 31, 11))
cd.add_series("$0.015 / msg", (74, 63, 52, 36, 8, -19))
ch = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(0.6), Inches(1.6), Inches(7.6), Inches(5.1), cd).chart
ch.has_legend, ch.legend.position, ch.legend.include_in_layout = True, XL_LEGEND_POSITION.BOTTOM, False
ch.value_axis.has_major_gridlines = True
ch.value_axis.tick_labels.font.size = Pt(11)
ch.category_axis.tick_labels.font.size = Pt(11)
for i, color in enumerate([RGBColor(0x0E, 0xA5, 0xA4), BRAND, RGBColor(0xD9, 0x48, 0x7A)]):
    ser = ch.series[i]
    ser.format.line.color.rgb = color
    ser.format.line.width = Pt(2.5)
text(s, 0.6, 6.55, 7.6, 0.4, "Professional plan gross margin % (y) vs utilisation of the 10,000-message allowance (x)", 11, color=MUTED)
bullets(s, 8.5, 1.8, 4.3, 5, ["At Base cost, Pro margin is 63% at typical usage but 11% at full usage", "Plan limits are a promise of maximum cost",
                              "Recommendation: include 5,000 messages + $50 credit packs (≈55% margin)", "Keep routing cheap models and caching; watch cost per outcome weekly"], 14)

# 11 Roadmap
s = base("Roadmap", "Plan, not commitment")
for i, (t, w, items) in enumerate([("MVP — built", "M0", ["Cited assistant & KB", "Agents + approvals", "Workflows", "Data NL→SQL", "Billing & admin"]),
                                   ("V1 — design partners & India", "M1–M3", ["Monitoring, streaming", "RLS, MFA", "Razorpay INR", "Credit packs", "Private evals, Drive"]),
                                   ("V2 — connected ops", "M4–M8", ["Jira/Confluence/HubSpot", "Scheduled agents", "Multi-table data", "SSO/SCIM", "ROI report"]),
                                   ("Future", "M9+", ["Operations radar", "AI-suggested workflows", "Vertical packs", "India data residency"])]):
    x = 0.6 + i * 3.1
    box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(1.8), Inches(2.9), Inches(4.6))
    box.fill.solid(); box.fill.fore_color.rgb = SOFT if i else RGBColor(0xE8, 0xF7, 0xEE); box.line.color.rgb = LINE
    text(s, x + 0.15, 1.9, 2.6, 0.5, w, 12, True, BRAND)
    text(s, x + 0.15, 2.25, 2.6, 0.8, t, 16, True)
    bullets(s, x + 0.15, 3.1, 2.6, 3.2, items, 13)

# 12 Risks
s = base("Top risks & mitigations", "Risk management")
table(s, 0.6, 1.7, 12.1, [["Risk", "Prob.", "Impact", "Mitigation"], ["Wrong answers on customer docs", "Med", "High", "Citations, 'not found', private evals, feedback loop"],
                          ["Cross-tenant leakage", "Low", "Critical", "Org-scoped queries + tests; RLS in V1; pen-test"],
                          ["Margin erosion from heavy users", "Med", "High", "Routing, caching, caps, credit packs, cost alerts"],
                          ["Suites bundle similar features", "High", "High", "Governance + outcomes + India focus; integrate with suites"],
                          ["Provider outage", "Med", "Med", "Multi-provider fallback; graceful demo degrade"],
                          ["DPDP compliance gaps", "Med", "High", "Privacy review, consent records, breach runbook"]], [4.0, 1.0, 1.2, 5.9], 13)

# 13 Quality evidence
s = base("Quality evidence (measured)", "Engineering execution")
table(s, 0.6, 1.7, 6.6, [["Check", "Result"], ["Backend tests (pytest)", "90 passed · 78% coverage"], ["E2E journeys (Playwright)", "8/8 dev + Docker prod stack"],
                         ["API suite (Newman)", "21 requests, 0 failures"], ["AI eval (demo engine)", "28/29 cases"], ["Load (20 concurrent)", "0% errors · RAG p95 243 ms"],
                         ["Dependency audits", "0 known vulnerabilities"], ["UI console errors (27 screens)", "0"]], [3.4, 3.2], 13)
bullets(s, 7.6, 1.8, 5.2, 5, ["12 defects found & fixed in testing (e.g. migration dropping vector indexes, stale AI cache, unlabeled form fields)",
                              "Eval measures the pipeline on a synthetic corpus — real-provider and customer-corpus evals are next",
                              "Not yet tested: live LLMs, Stripe live, OAuth round-trips, load > 20 users"], 14)

# 14 Recommendations
s = base("Strategic recommendations", "Decisions requested")
bullets(s, 0.6, 1.8, 12, 5, ["Approve pricing change before launch: Pro 5,000 included messages + credit packs; Starter acquired organically only",
                             "Recruit 5 design partners (India, 20–100 staff, ops-heavy) under DPA; build private eval sets with them",
                             "Fund real-provider evaluation (~40 calls/run nightly) and observability before handling customer data",
                             "Sequence V1: monitoring → streaming → RLS/MFA → Razorpay → credit packs → Drive/Slack",
                             "Gate expansion bets (AI-suggested workflows, vertical packs) on experiment results, not intuition",
                             "Success by M3: ≥40% week-1 outcome rate, ≥6% trial→paid, ≥65% gross margin, zero isolation incidents"], 17)

out = ROOT / "docs" / "business" / "NEXORA_Executive_Review.pptx"
prs.save(out)
print("wrote", out, len(prs.slides), "slides")
