"""Dataset ingestion, profiling, cleaning recommendations, NL→SQL and safe execution."""
import csv
import io
import json
import math
import re
import time
import uuid
from datetime import datetime, date
from statistics import mean, median
from sqlalchemy import text, create_engine, select
from sqlalchemy.orm import Session
from app.ai.gateway import generate
from app.ai.providers.base import LLMRequest, ChatMessage
from app.core.config import get_settings
from app.core.errors import bad_request
from app.data.sqlguard import validate_and_rewrite, UnsafeSQL, MAX_ROWS
from app.models import Dataset, DatasetQuery

MAX_ROWS_INGEST = 200_000
MAX_COLS = 100
_ro_engine = None


def ro_engine():
    global _ro_engine
    s = get_settings()
    if _ro_engine is None and s.analytics_readonly_database_url:
        _ro_engine = create_engine(s.analytics_readonly_database_url, pool_pre_ping=True, pool_size=5)
    return _ro_engine


def ident(name: str, used: set) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_") or "col"
    if s[0].isdigit():
        s = "c_" + s
    s = s[:50]
    base, i = s, 2
    while s in used:
        s, i = f"{base}_{i}", i + 1
    used.add(s)
    return s


def parse_table(filename: str, data: bytes) -> tuple[list[str], list[list[str]]]:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "csv":
        try:
            txt = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            txt = data.decode("latin-1")
        try:
            dialect = csv.Sniffer().sniff(txt[:5000], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(txt), dialect))
    elif ext == "xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = [["" if v is None else (v.isoformat() if isinstance(v, (datetime, date)) else str(v)) for v in r] for r in ws.iter_rows(values_only=True)]
    else:
        raise bad_request("Datasets must be CSV or XLSX", "unsupported_file_type")
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if len(rows) < 2:
        raise bad_request("The file needs a header row and at least one data row")
    header = [str(h).strip() or f"column_{i + 1}" for i, h in enumerate(rows[0])]
    if len(header) > MAX_COLS:
        raise bad_request(f"Too many columns (max {MAX_COLS})")
    body = [(r + [""] * len(header))[: len(header)] for r in rows[1: MAX_ROWS_INGEST + 1]]
    return header, body


_num_re = re.compile(r"^[-+]?[\$₹€£]?\s?\d[\d,]*(\.\d+)?%?$")
DATE_FORMATS = ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%b %d %Y", "%d %b %Y"]


def to_num(v: str):
    v = v.strip().replace(",", "").replace("$", "").replace("₹", "").replace("€", "").replace("£", "").rstrip("%").strip()
    try:
        return float(v)
    except ValueError:
        return None


def to_date(v: str):
    v = v.strip()[:19]
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(v, f).date()
        except ValueError:
            continue
    return None


def infer(header: list[str], body: list[list[str]]) -> list[dict]:
    used: set = set()
    cols = []
    for i, h in enumerate(header):
        vals = [r[i].strip() for r in body]
        non_empty = [v for v in vals if v != ""]
        sample = non_empty[:2000]
        nums = [v for v in sample if _num_re.match(v)]
        dates = [v for v in sample if to_date(v)] if len(nums) < len(sample) * 0.9 else []
        bools = [v for v in sample if v.lower() in ("true", "false", "yes", "no", "0", "1")]
        if sample and len(nums) >= 0.95 * len(sample):
            all_int = all(float(to_num(v) or 0).is_integer() for v in nums[:500])
            typ = "integer" if all_int and max((abs(to_num(v) or 0) for v in nums[:500]), default=0) < 2**31 else "numeric"
        elif sample and len(dates) >= 0.9 * len(sample):
            typ = "date"
        elif sample and len(bools) == len(sample) and len({b.lower() for b in bools}) <= 2:
            typ = "boolean"
        else:
            typ = "text"
        distinct = len(set(non_empty))
        name = ident(h, used)
        if typ == "date":
            kind = "date"
        elif typ in ("integer", "numeric"):
            kind = "identifier" if re.search(r"(^|_)(id|code|zip|pin|phone|year)($|_)", name) or (distinct == len(non_empty) and typ == "integer" and len(non_empty) > 20) else "measure"
        elif typ == "boolean":
            kind = "dimension"
        else:
            avg_len = sum(len(v) for v in sample) / max(len(sample), 1)
            if any("@" in v for v in sample[:50]) and re.search(r"email", name + " " + h.lower()):
                kind = "pii"
            elif avg_len > 60:
                kind = "free_text"
            elif distinct == len(non_empty) and len(non_empty) > 20:
                kind = "identifier"
            else:
                kind = "dimension"
        cols.append({"name": name, "label": h, "type": typ, "kind": kind, "index": i})
    return cols


def profile(cols: list[dict], body: list[list[str]]) -> tuple[dict, list[dict]]:
    n = len(body)
    recs, prof = [], {}
    seen, dup = set(), 0
    for r in body:
        k = tuple(r)
        dup += k in seen
        seen.add(k)
    if dup:
        recs.append({"severity": "medium", "column": None, "issue": f"{dup} duplicate rows", "suggestion": "Remove exact duplicate rows before analysis."})
    for c in cols:
        vals = [r[c["index"]].strip() for r in body]
        nulls = sum(1 for v in vals if v == "")
        non = [v for v in vals if v != ""]
        p = {"nulls": nulls, "null_pct": round(nulls / n * 100, 1) if n else 0, "distinct": len(set(non))}
        if c["type"] in ("integer", "numeric"):
            nums = [x for x in (to_num(v) for v in non) if x is not None]
            if nums:
                s = sorted(nums)
                q1, q3 = s[len(s) // 4], s[(3 * len(s)) // 4]
                iqr = q3 - q1
                outliers = sum(1 for x in nums if x < q1 - 3 * iqr or x > q3 + 3 * iqr) if iqr else 0
                p.update({"min": s[0], "max": s[-1], "mean": round(mean(nums), 4), "median": median(nums), "outliers": outliers})
                if outliers:
                    recs.append({"severity": "low", "column": c["name"], "issue": f"{outliers} extreme outliers (>3×IQR)",
                                 "suggestion": "Check for data-entry errors or unit mismatches."})
            bad = len(non) - len(nums)
            if bad:
                recs.append({"severity": "medium", "column": c["name"], "issue": f"{bad} non-numeric values in a numeric column",
                             "suggestion": "These are stored as NULL; correct them at the source."})
        elif c["type"] == "date":
            ds = [d for d in (to_date(v) for v in non) if d]
            if ds:
                p.update({"min": min(ds).isoformat(), "max": max(ds).isoformat()})
        else:
            counts: dict[str, int] = {}
            for v in non:
                counts[v] = counts.get(v, 0) + 1
            p["top_values"] = sorted(counts.items(), key=lambda x: -x[1])[:8]
            lowered = {}
            for v in counts:
                lowered.setdefault(v.lower().strip(), set()).add(v)
            inconsistent = [vs for vs in lowered.values() if len(vs) > 1]
            if inconsistent and c["kind"] == "dimension":
                recs.append({"severity": "medium", "column": c["name"], "issue": f"Inconsistent casing/spacing, e.g. {sorted(inconsistent[0])[:3]}",
                             "suggestion": "Standardise category labels so groupings are accurate."})
            if c["kind"] == "pii":
                recs.append({"severity": "high", "column": c["name"], "issue": "Contains personal data (emails)",
                             "suggestion": "Confirm you have a lawful basis (DPDP/GDPR) to process this data, or drop the column."})
        if p["null_pct"] > 20:
            recs.append({"severity": "high" if p["null_pct"] > 50 else "medium", "column": c["name"], "issue": f"{p['null_pct']}% missing values",
                         "suggestion": "Impute, exclude, or fix the data source; results using this column may be biased."})
        prof[c["name"]] = p
    return prof, recs


def sql_type(t: str) -> str:
    return {"integer": "BIGINT", "numeric": "DOUBLE PRECISION", "date": "DATE", "boolean": "BOOLEAN"}.get(t, "TEXT")


def convert(v: str, t: str):
    v = v.strip()
    if v == "":
        return None
    if t in ("integer", "numeric"):
        x = to_num(v)
        return None if x is None else (int(x) if t == "integer" else x)
    if t == "date":
        return to_date(v)
    if t == "boolean":
        return v.lower() in ("true", "yes", "1")
    return v[:10000]


def ingest(db: Session, org_id, user_id, name: str, filename: str, data: bytes) -> Dataset:
    header, body = parse_table(filename, data)
    cols = infer(header, body)
    prof, recs = profile(cols, body)
    table = f"ds_{uuid.uuid4().hex[:20]}"
    db.execute(text("CREATE SCHEMA IF NOT EXISTS datasets"))
    coldefs = ", ".join(f'"{c["name"]}" {sql_type(c["type"])}' for c in cols)
    db.execute(text(f'CREATE TABLE datasets."{table}" ({coldefs})'))
    names = ", ".join(f'"{c["name"]}"' for c in cols)
    params = ", ".join(f":p{i}" for i in range(len(cols)))
    stmt = text(f'INSERT INTO datasets."{table}" ({names}) VALUES ({params})')
    batch = []
    for r in body:
        batch.append({f"p{i}": convert(r[c["index"]], c["type"]) for i, c in enumerate(cols)})
        if len(batch) >= 2000:
            db.execute(stmt, batch)
            batch = []
    if batch:
        db.execute(stmt, batch)
    try:
        with db.begin_nested():  # savepoint: a failed GRANT must not abort the upload transaction
            db.execute(text(f'GRANT SELECT ON datasets."{table}" TO nexora_readonly'))
    except Exception:
        pass  # read-only role is optional (some hosted Postgres plans cannot create roles)
    ds = Dataset(org_id=org_id, name=name[:200], filename=filename[:300], table_name=table, row_count=len(body),
                 columns=[{k: v for k, v in c.items() if k != "index"} for c in cols], profile=prof, recommendations=recs, created_by=user_id)
    db.add(ds)
    db.flush()
    return ds


def find_dataset(db: Session, org_id, name_or_id: str) -> Dataset | None:
    try:
        ds = db.get(Dataset, uuid.UUID(str(name_or_id)))
        if ds and ds.org_id == org_id:
            return ds
    except ValueError:
        pass
    rows = db.scalars(select(Dataset).where(Dataset.org_id == org_id)).all()
    nm = (name_or_id or "").lower().strip()
    return next((d for d in rows if d.name.lower() == nm), None) or next((d for d in rows if nm and nm in d.name.lower()), None) or (rows[0] if len(rows) == 1 else None)


def schema_for(ds: Dataset) -> dict:
    return {"table": "data", "columns": ds.columns, "row_count": ds.row_count}


SQL_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["sql", "explanation", "chart_type", "x", "y"],
              "properties": {"sql": {"type": "string"}, "explanation": {"type": "string"},
                             "chart_type": {"type": "string", "enum": ["none", "bar", "line", "pie", "table"]},
                             "x": {"type": "string"}, "y": {"type": "string"}}}


def generate_sql(db: Session, org_id, user_id, ds: Dataset, question: str, feature: str) -> dict:
    sch = schema_for(ds)
    cols = "\n".join(f'- "{c["name"]}" {c["type"]} ({c["kind"]}; original header: {c["label"]})' for c in ds.columns)
    sample = {k: (v.get("top_values") or [])[:3] for k, v in ds.profile.items() if v.get("top_values")}
    system = ("You translate business questions into a single PostgreSQL SELECT over one table named data. Rules: SELECT only; never modify data; "
              "use only the listed columns, double-quoted; use date_trunc for time series; aggregate and ORDER BY sensibly; LIMIT 100 unless asked. "
              "If the question cannot be answered from the columns, return SELECT 'not answerable' AS message and explain why.")
    prompt = f"Table data ({ds.row_count} rows). Columns:\n{cols}\nExample category values: {json.dumps(sample)[:1500]}\n\nQuestion: {question}"
    r = generate(db, LLMRequest(messages=[ChatMessage(role="user", content=prompt)], system=system, task_type="sql", json_schema=SQL_SCHEMA,
                                metadata={"demo_handler": "nl_to_sql", "schema": sch, "text": question}),
                 org_id=org_id, user_id=user_id, feature=feature)
    p = r.parsed or {}
    chart = p.get("chart")
    if chart is None and p.get("chart_type") not in (None, "none", "table"):
        chart = {"type": p["chart_type"], "x": p.get("x"), "y": p.get("y")}
    return {"sql": p.get("sql", ""), "explanation": p.get("explanation", ""), "chart": chart, "model": r.model, "demo": r.demo}


def execute_safe(db: Session, ds: Dataset, sql: str) -> tuple[list[str], list[list], str]:
    """Validate, then run on a dedicated connection inside a READ ONLY transaction that is always rolled back."""
    allowed = {c["name"].lower() for c in ds.columns}
    safe_sql = validate_and_rewrite(sql, ds.table_name, allowed)
    from app.core.db import engine
    eng = ro_engine() or engine
    with eng.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = '5s'"))
            conn.execute(text("SET LOCAL search_path = datasets"))
            res = conn.execute(text(safe_sql))
            columns = list(res.keys())
            rows = [[_jsonable(v) for v in row] for row in res.fetchmany(MAX_ROWS)]
        finally:
            trans.rollback()
    return columns, rows, safe_sql


def _jsonable(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, "__float__") and not isinstance(v, (int, float, bool)):
        return float(v)
    return v


def auto_chart(columns: list[str], rows: list[list], hint: dict | None) -> dict | None:
    if hint and hint.get("x") in columns and hint.get("y") in columns:
        return hint
    if len(columns) >= 2 and rows:
        num_idx = [i for i in range(len(columns)) if all(isinstance(r[i], (int, float)) or r[i] is None for r in rows[:50])]
        cat_idx = [i for i in range(len(columns)) if i not in num_idx]
        if num_idx and cat_idx:
            x = columns[cat_idx[0]]
            return {"type": "line" if re.search(r"month|date|week|day|year", x) else "bar", "x": x, "y": columns[num_idx[0]]}
    return None


def run_nl_query(db: Session, org_id, user_id, ds: Dataset, question: str, feature: str = "data") -> dict:
    t0 = time.perf_counter()
    gen = generate_sql(db, org_id, user_id, ds, question, feature)
    q = DatasetQuery(org_id=org_id, dataset_id=ds.id, user_id=user_id, question=question, generated_sql=gen["sql"], status="running")
    db.add(q)
    try:
        columns, rows, safe = execute_safe(db, ds, gen["sql"])
        q.status, q.executed_sql, q.row_count, q.explanation = "succeeded", safe, len(rows), gen["explanation"]
        q.chart = auto_chart(columns, rows, gen.get("chart"))
    except UnsafeSQL as e:
        q.status, q.error = "rejected", str(e)
        columns, rows, safe = [], [], None
    except Exception as e:
        q.status, q.error = "failed", str(getattr(e, "orig", e)).splitlines()[0][:500]
        columns, rows, safe = [], [], None
    q.latency_ms = int((time.perf_counter() - t0) * 1000)
    db.flush()
    return {"id": str(q.id), "question": question, "sql": safe or gen["sql"], "status": q.status, "error": q.error, "explanation": gen["explanation"],
            "columns": columns, "rows": rows, "row_count": len(rows), "chart": q.chart, "model": gen["model"], "demo": gen["demo"],
            "latency_ms": q.latency_ms}
