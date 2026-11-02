import io


def make_pdf(pages: list[str]) -> bytes:
    """Minimal valid PDF with one text page per entry (Helvetica)."""
    objs = []
    kids = []
    n_pages = len(pages)
    # 1 catalog, 2 pages, 3 font, then (page, content) pairs
    page_ids = [4 + i * 2 for i in range(n_pages)]
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(("<< /Type /Pages /Kids [" + " ".join(f"{p} 0 R" for p in page_ids) + f"] /Count {n_pages} >>").encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, txt in enumerate(pages):
        lines = [l.replace("(", "[").replace(")", "]") for l in txt.split("\n")]
        stream = "BT /F1 11 Tf 50 750 Td 14 TL " + " ".join(f"({l}) Tj T*" for l in lines) + " ET"
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_ids[i] + 1} 0 R >>".encode())
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream".encode())
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def make_docx(sections: list[tuple[str, str]]) -> bytes:
    import docx
    d = docx.Document()
    for heading, body in sections:
        d.add_heading(heading, level=1)
        for para in body.split("\n"):
            d.add_paragraph(para)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def make_xlsx(rows: list[list]) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


SALES_CSV = """order_id,order_date,customer,product,category,quantity,revenue,region
1001,2026-01-05,Asha Traders,Widget Pro,Hardware,10,1200.50,North
1002,2026-01-12,Bharat Retail,Cloud Seat,Software,5,2500,South
1003,2026-01-20,Asha Traders,Widget Pro,Hardware,4,480,North
1004,2026-02-02,Chola Foods,Support Plan,Services,1,900,East
1005,2026-02-14,Bharat Retail,Cloud Seat,Software,8,4000,South
1006,2026-02-21,Deccan Labs,Widget Mini,Hardware,20,1000,West
1007,2026-03-03,Asha Traders,Support Plan,Services,2,1800,North
1008,2026-03-09,Deccan Labs,Cloud Seat,Software,12,6000,West
1009,2026-03-18,Chola Foods,Widget Mini,hardware,6,300,East
1010,2026-03-28,Bharat Retail,Widget Pro,Hardware,3,360,South
"""

POLICY_MD = """# Travel & Expense Policy

## Approval limits
Expenses below 500 USD can be approved by a line manager. Expenses between 500 and 5000 USD require director approval.
Anything above 5000 USD requires CFO approval and a written business case.

## Reimbursement
Employees must submit receipts within 30 days of the expense. Reimbursements are paid in the next payroll cycle.

## Remote work equipment
Each employee receives a one-time home office allowance of 300 USD for ergonomic equipment.
"""

MEETING_NOTES = """Weekly ops sync — 2 Nov
- Priya to send the revised vendor proposal by Friday.
- Rahul will update the onboarding checklist next week.
- Action: review Q3 churn numbers (urgent).
- Discussed hiring plan; no decision yet.
- Meera to schedule the security audit with the vendor tomorrow.
"""
