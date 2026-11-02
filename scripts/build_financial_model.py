"""Builds docs/business/NEXORA_Financial_Model.xlsx — an editable, formula-driven 36-month SaaS model with
Conservative / Base / Optimistic scenarios. ALL inputs are hypothetical planning assumptions (blue cells); no actuals exist.
Run: backend/.venv/bin/python scripts/build_financial_model.py"""
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

OUT = Path(__file__).resolve().parents[1] / "docs" / "business" / "NEXORA_Financial_Model.xlsx"
BLUE = Font(color="1F3FBF")
BOLD = Font(bold=True)
HDR = PatternFill("solid", fgColor="E8EAF6")
INPUT = PatternFill("solid", fgColor="FFF8E1")
thin = Border(bottom=Side(style="thin", color="DDDDDD"))

# name, label, conservative, base, optimistic, unit, note
A = [
    ("price_starter", "Starter price / month", 49, 49, 49, "USD", "List price (MONETISATION_STRATEGY.md)"),
    ("price_pro", "Professional price / month", 199, 199, 199, "USD", ""),
    ("price_ent", "Enterprise average contract / month", 1200, 1500, 2000, "USD", "Assumption: custom contracts"),
    ("signups_m1", "Workspace signups in month 1", 80, 120, 200, "orgs", "Assumption: founder-led + content + Product Hunt"),
    ("signup_growth", "Signup growth MoM — year 1 (halves in Y2, halves again in Y3)", 0.06, 0.10, 0.14, "%", "Assumption; growth decay prevents unrealistic compounding"),
    ("conv", "Trial/Free → paid conversion (within cohort)", 0.04, 0.06, 0.09, "%", "Benchmark range for PLG B2B SaaS 2-10% (hypothesis)"),
    ("mix_starter", "New paid mix: Starter", 0.70, 0.65, 0.58, "%", ""),
    ("mix_pro", "New paid mix: Professional", 0.28, 0.32, 0.37, "%", ""),
    ("mix_ent", "New paid mix: Enterprise", 0.02, 0.03, 0.05, "%", ""),
    ("churn_starter", "Monthly logo churn: Starter", 0.05, 0.04, 0.03, "%", "SMB churn assumption"),
    ("churn_pro", "Monthly logo churn: Professional", 0.035, 0.025, 0.02, "%", ""),
    ("churn_ent", "Monthly logo churn: Enterprise", 0.015, 0.01, 0.008, "%", ""),
    ("cac", "CAC per new self-serve org (Starter/Pro)", 800, 550, 350, "USD", "Content/SEO + paid + onboarding"),
    ("cac_ent", "CAC per new Enterprise org (sales-led)", 7000, 5000, 4000, "USD", "Founder/AE time + pilots"),
    ("ai_cost_msg", "Blended AI cost per AI message", 0.015, 0.009, 0.006, "USD", "From model routing mix (AI_ARCHITECTURE.md §cost)"),
    ("ai_cost_run", "AI cost per agent run", 0.06, 0.04, 0.03, "USD", "~3-5 model calls per run"),
    ("msgs_starter", "AI messages / Starter org / month", 800, 700, 600, "count", "≈35% of 2,000 plan limit"),
    ("msgs_pro", "AI messages / Pro org / month", 4000, 3500, 3000, "count", "≈35% of 10,000 plan limit"),
    ("msgs_ent", "AI messages / Enterprise org / month", 18000, 15000, 12000, "count", ""),
    ("runs_starter", "Agent runs / Starter org / month", 80, 60, 50, "count", ""),
    ("runs_pro", "Agent runs / Pro org / month", 700, 600, 500, "count", ""),
    ("runs_ent", "Agent runs / Enterprise org / month", 3000, 2500, 2000, "count", ""),
    ("infra_starter", "Variable infra / Starter org / month", 4, 3, 2.5, "USD", "DB, storage, compute share"),
    ("infra_pro", "Variable infra / Pro org / month", 12, 10, 8, "USD", ""),
    ("infra_ent", "Variable infra / Enterprise org / month", 80, 60, 50, "USD", ""),
    ("free_ratio", "Active free orgs per paying org", 4, 3, 2.5, "x", "Free tier cost is a growth cost"),
    ("free_msgs", "AI messages / active free org / month", 60, 40, 35, "count", "Free limit 150"),
    ("pay_fee", "Payment processing fee", 0.035, 0.03, 0.025, "%", "Stripe/Razorpay range (verify)"),
    ("support_per_org", "Support cost / paying org / month", 4, 3, 2, "USD", ""),
    ("fixed_infra", "Fixed infra & tooling / month", 600, 400, 400, "USD", "Monitoring, CI, base DB"),
    ("team_y1", "Team cost / month — year 1", 20000, 18000, 18000, "USD", "Lean India-based team (assumption)"),
    ("team_y2", "Team cost / month — year 2", 38000, 35000, 40000, "USD", ""),
    ("team_y3", "Team cost / month — year 3", 60000, 55000, 70000, "USD", ""),
    ("start_cash", "Starting cash (pre-seed)", 250000, 250000, 250000, "USD", "Hypothetical"),
]
IDX = {}


def build():
    wb = Workbook()
    ws = wb.active
    ws.title = "Assumptions"
    ws["A1"] = "NEXORA AI — Financial model (HYPOTHETICAL — no actual customers or revenue)"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = "Active scenario →"
    ws["B2"] = "Base"
    ws["B2"].fill = INPUT
    ws["B2"].font = BOLD
    dv = DataValidation(type="list", formula1='"Conservative,Base,Optimistic"', allow_blank=False)
    ws.add_data_validation(dv)
    dv.add("B2")
    ws["C2"] = "Change B2 to switch every sheet. Blue/yellow cells are inputs."
    heads = ["Key", "Assumption", "Conservative", "Base", "Optimistic", "ACTIVE", "Unit", "Source / note"]
    for i, h in enumerate(heads, 1):
        c = ws.cell(row=4, column=i, value=h)
        c.font, c.fill = BOLD, HDR
    for r, (k, label, c_, b, o, unit, note) in enumerate(A, start=5):
        IDX[k] = r
        ws.cell(row=r, column=1, value=k).font = Font(color="888888", size=9)
        ws.cell(row=r, column=2, value=label)
        for col, v in zip((3, 4, 5), (c_, b, o)):
            cell = ws.cell(row=r, column=col, value=v)
            cell.font, cell.fill = BLUE, INPUT
            if unit == "%":
                cell.number_format = "0.0%"
        f = ws.cell(row=r, column=6, value=f'=INDEX(C{r}:E{r},MATCH($B$2,{{"Conservative","Base","Optimistic"}},0))')
        f.font = BOLD
        if unit == "%":
            f.number_format = "0.0%"
        ws.cell(row=r, column=7, value=unit)
        ws.cell(row=r, column=8, value=note)
    for col, w in zip("ABCDEFGH", (16, 44, 14, 12, 12, 12, 8, 52)):
        ws.column_dimensions[col].width = w

    def a(k):
        return f"Assumptions!$F${IDX[k]}"

    # ---------------- Projection ----------------
    p = wb.create_sheet("Projection")
    cols = ["Month", "Signups", "New paid", "New Starter", "New Pro", "New Ent", "Starter orgs", "Pro orgs", "Ent orgs", "Paying orgs",
            "MRR", "ARR", "AI COGS (paid)", "AI COGS (free tier)", "Variable infra", "Payment fees", "Support", "Fixed infra",
            "Gross profit", "Gross margin %", "Acquisition spend", "Team cost", "Net income", "Cumulative cash"]
    for i, h in enumerate(cols, 1):
        c = p.cell(row=1, column=i, value=h)
        c.font, c.fill = BOLD, HDR
        c.alignment = Alignment(wrap_text=True, vertical="top")
        p.column_dimensions[get_column_letter(i)].width = 13
    for m in range(1, 37):
        r = m + 1
        prev = r - 1
        p.cell(row=r, column=1, value=m)
        if m == 1:
            p.cell(row=r, column=2, value=f"={a('signups_m1')}")
        else:
            p.cell(row=r, column=2, value=f"=B{prev}*(1+{a('signup_growth')}*IF(A{r}<=12,1,IF(A{r}<=24,0.5,0.25)))")
        p.cell(row=r, column=3, value=f"=B{r}*{a('conv')}")
        p.cell(row=r, column=4, value=f"=C{r}*{a('mix_starter')}")
        p.cell(row=r, column=5, value=f"=C{r}*{a('mix_pro')}")
        p.cell(row=r, column=6, value=f"=C{r}*{a('mix_ent')}")
        for col, new, churn in ((7, "D", "churn_starter"), (8, "E", "churn_pro"), (9, "F", "churn_ent")):
            L = get_column_letter(col)
            p.cell(row=r, column=col, value=(f"={new}{r}" if m == 1 else f"={L}{prev}*(1-{a(churn)})+{new}{r}"))
        p.cell(row=r, column=10, value=f"=G{r}+H{r}+I{r}")
        p.cell(row=r, column=11, value=f"=G{r}*{a('price_starter')}+H{r}*{a('price_pro')}+I{r}*{a('price_ent')}")
        p.cell(row=r, column=12, value=f"=K{r}*12")
        p.cell(row=r, column=13, value=f"=G{r}*({a('msgs_starter')}*{a('ai_cost_msg')}+{a('runs_starter')}*{a('ai_cost_run')})"
                                     f"+H{r}*({a('msgs_pro')}*{a('ai_cost_msg')}+{a('runs_pro')}*{a('ai_cost_run')})"
                                     f"+I{r}*({a('msgs_ent')}*{a('ai_cost_msg')}+{a('runs_ent')}*{a('ai_cost_run')})")
        p.cell(row=r, column=14, value=f"=J{r}*{a('free_ratio')}*{a('free_msgs')}*{a('ai_cost_msg')}")
        p.cell(row=r, column=15, value=f"=G{r}*{a('infra_starter')}+H{r}*{a('infra_pro')}+I{r}*{a('infra_ent')}")
        p.cell(row=r, column=16, value=f"=K{r}*{a('pay_fee')}")
        p.cell(row=r, column=17, value=f"=J{r}*{a('support_per_org')}")
        p.cell(row=r, column=18, value=f"={a('fixed_infra')}")
        p.cell(row=r, column=19, value=f"=K{r}-SUM(M{r}:R{r})")
        p.cell(row=r, column=20, value=f"=IF(K{r}=0,0,S{r}/K{r})")
        p.cell(row=r, column=21, value=f"=(D{r}+E{r})*{a('cac')}+F{r}*{a('cac_ent')}")
        p.cell(row=r, column=22, value=f"=IF(A{r}<=12,{a('team_y1')},IF(A{r}<=24,{a('team_y2')},{a('team_y3')}))")
        p.cell(row=r, column=23, value=f"=S{r}-U{r}-V{r}")
        p.cell(row=r, column=24, value=(f"={a('start_cash')}+W{r}" if m == 1 else f"=X{prev}+W{r}"))
        for col in range(2, 25):
            p.cell(row=r, column=col).number_format = "0.0%" if col == 20 else "#,##0"
    p.freeze_panes = "B2"

    # ---------------- Unit economics ----------------
    u = wb.create_sheet("Unit economics")
    u["A1"] = "Per-plan unit economics (active scenario)"
    u["A1"].font = Font(bold=True, size=12)
    hdr = ["Metric", "Starter", "Professional", "Enterprise"]
    for i, h in enumerate(hdr, 1):
        c = u.cell(row=3, column=i, value=h)
        c.font, c.fill = BOLD, HDR
    rows = [
        ("Price / month", "price_starter", "price_pro", "price_ent", None),
        ("AI cost / month", f"={a('msgs_starter')}*{a('ai_cost_msg')}+{a('runs_starter')}*{a('ai_cost_run')}",
         f"={a('msgs_pro')}*{a('ai_cost_msg')}+{a('runs_pro')}*{a('ai_cost_run')}", f"={a('msgs_ent')}*{a('ai_cost_msg')}+{a('runs_ent')}*{a('ai_cost_run')}", "f"),
        ("Infra + support / month", f"={a('infra_starter')}+{a('support_per_org')}", f"={a('infra_pro')}+{a('support_per_org')}", f"={a('infra_ent')}+{a('support_per_org')}", "f"),
        ("Payment fees / month", "=B4*" + a("pay_fee"), "=C4*" + a("pay_fee"), "=D4*" + a("pay_fee"), "f"),
        ("Gross margin / month", "=B4-B5-B6-B7", "=C4-C5-C6-C7", "=D4-D5-D6-D7", "f"),
        ("Gross margin %", "=B8/B4", "=C8/C4", "=D8/D4", "pct"),
        ("Monthly churn", "churn_starter", "churn_pro", "churn_ent", None),
        ("Expected lifetime (months)", "=1/B10", "=1/C10", "=1/D10", "f"),
        ("LTV (gross-margin basis)", "=B8*B11", "=C8*C11", "=D8*D11", "f"),
        ("CAC", "cac", "cac", "cac_ent", None),
        ("LTV / CAC", "=B12/B13", "=C12/C13", "=D12/D13", "x"),
        ("CAC payback (months)", "=B13/B8", "=C13/C8", "=D13/D8", "f"),
    ]
    for i, (label, s, pr, e, kind) in enumerate(rows, start=4):
        u.cell(row=i, column=1, value=label)
        for col, v in zip((2, 3, 4), (s, pr, e)):
            val = v if (kind or str(v).startswith("=")) else f"={a(v)}"
            c = u.cell(row=i, column=col, value=val)
            c.number_format = "0.0%" if kind == "pct" or label == "Monthly churn" else ("0.0x" if kind == "x" else "#,##0.00")
    u["A18"] = "Blended (month 36, active scenario)"
    u["A18"].font = BOLD
    u["A19"], u["B19"] = "ARPA (MRR / paying orgs)", "=Projection!K37/Projection!J37"
    u["A20"], u["B20"] = "Gross margin %", "=Projection!T37"
    u["A21"], u["B21"] = "ARR at month 36", "=Projection!L37"
    u["A22"], u["B22"] = "Paying orgs at month 36", "=Projection!J37"
    u["A23"], u["B23"] = "First month net income ≥ 0 (break-even)", '=IFERROR(INDEX(Projection!A2:A37,MATCH(TRUE,INDEX(Projection!W2:W37>=0,0),0)),"Not within 36 months")'
    u["A24"], u["B24"] = "Minimum cumulative cash (funding need)", "=MIN(Projection!X2:X37)"
    for c in ("B19", "B21", "B22", "B24"):
        u[c].number_format = "#,##0"
    u["B20"].number_format = "0.0%"
    u.column_dimensions["A"].width = 40
    for c in "BCD":
        u.column_dimensions[c].width = 16

    # ---------------- Sensitivity ----------------
    s = wb.create_sheet("Sensitivity")
    s["A1"] = "Professional plan gross margin % vs AI cost per message (rows) and utilisation of the 10,000-message limit (columns)"
    s["A1"].font = BOLD
    s["A2"] = "Agent runs scale with utilisation (600 runs at 35%). Infra+support and payment fees from active scenario."
    utils = [0.15, 0.25, 0.35, 0.50, 0.75, 1.00]
    costs = [0.003, 0.006, 0.009, 0.012, 0.015, 0.020, 0.030]
    s.cell(row=4, column=1, value="AI $/msg ↓  utilisation →").font = BOLD
    for j, ut in enumerate(utils, start=2):
        c = s.cell(row=4, column=j, value=ut)
        c.number_format, c.font, c.fill = "0%", BOLD, HDR
    for i, cst in enumerate(costs, start=5):
        c = s.cell(row=i, column=1, value=cst)
        c.number_format, c.font, c.fill = "$0.000", BOLD, HDR
        for j in range(2, 2 + len(utils)):
            col = get_column_letter(j)
            f = (f"=({a('price_pro')}*(1-{a('pay_fee')})-{a('infra_pro')}-{a('support_per_org')}-10000*{col}$4*$A{i}"
                 f"-({a('runs_pro')}/0.35)*{col}$4*{a('ai_cost_run')})/{a('price_pro')}")
            s.cell(row=i, column=j, value=f).number_format = "0%"
    s.column_dimensions["A"].width = 26

    # ---------------- Market sizing ----------------
    mk = wb.create_sheet("Market sizing")
    rows = [
        ("Layer", "Definition", "Organisations", "Annual value / org (USD)", "Market (USD)", "Source / assumption"),
        ("TAM (global)", "SMBs & mid-market with 10-500 employees using cloud productivity tools", 9_000_000, 2400, "=C2*D2",
         "Assumption built from: US ~6.4M employer firms (SBA Advocacy via secondary source), India 7.3 crore Udyam registrations (MSME Ministry, Dec 2025) — only a small share are digital-first. Treat as order-of-magnitude."),
        ("SAM", "English-first digital SMBs in India, US, UK, SEA with 10-200 staff & an ops/knowledge problem", 1_200_000, 1800, "=C3*D3", "Assumption: ~13% of TAM orgs reachable by self-serve PLG"),
        ("SOM (3-yr)", "Realistic capture by a seed-stage PLG company", "=Projection!J37", "=Unit economics!B19*12", "=C4*D4", "Linked to the active scenario"),
    ]
    for i, row in enumerate(rows, start=1):
        for j, v in enumerate(row, start=1):
            c = mk.cell(row=i, column=j, value=v)
            if i == 1:
                c.font, c.fill = BOLD, HDR
            elif j in (3, 4, 5):
                c.number_format = "#,##0"
    mk["D4"] = "='Unit economics'!B19*12"
    for col, w in zip("ABCDEF", (14, 60, 16, 22, 20, 90)):
        mk.column_dimensions[col].width = w

    # ---------------- Notes ----------------
    n = wb.create_sheet("Read me")
    for i, line in enumerate([
        "NEXORA AI financial model — HYPOTHETICAL. There are no customers, revenue or real costs yet.",
        "Actual costs known today: only development-environment costs (not modelled). Every number in yellow is an assumption.",
        "How to use: pick a scenario in Assumptions!B2; edit yellow inputs; Projection, Unit economics, Sensitivity and Market sizing recalculate.",
        "AI cost per message is derived from the routing table (AI_ARCHITECTURE.md): ~60% balanced-tier chat, ~30% fast-tier tasks, ~10% frontier analysis, with prompt caching.",
        "Key sensitivity: Professional gross margin falls below 60% once blended AI cost exceeds ~$0.012/message at 35% utilisation — see Sensitivity sheet.",
    ], start=1):
        n.cell(row=i, column=1, value=line)
    n.column_dimensions["A"].width = 150
    wb.move_sheet("Read me", offset=-5)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
