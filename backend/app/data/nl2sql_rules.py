"""Deterministic NL→SQL used in demo mode (no LLM key) and as a test oracle. Handles common business question shapes."""
import re
from difflib import get_close_matches
from app.ai.textutil import keywords, stem


def _match_col(word_list: list[str], cols: list[dict], kinds: set[str] | None = None) -> dict | None:
    cands = [c for c in cols if not kinds or c["kind"] in kinds]
    names = {c["name"].lower(): c for c in cands}
    label_map = {}
    for c in cands:
        for token in re.split(r"[_\s]+", c["name"].lower()):
            label_map.setdefault(stem(token), c)
    for w in word_list:
        sw = stem(w)
        if w in names:
            return names[w]
        if sw in label_map:
            return label_map[sw]
        close = get_close_matches(w, list(names), n=1, cutoff=0.8)
        if close:
            return names[close[0]]
    return None


SYN = {"revenue": ["revenue", "sales", "amount", "total", "price", "value", "income"], "customer": ["customer", "client", "account", "buyer"],
       "product": ["product", "item", "sku"], "category": ["category", "segment", "type", "group"], "date": ["date", "month", "time", "day", "created", "order"]}


def _expand(words: list[str]) -> list[str]:
    out = list(words)
    for w in words:
        for syns in SYN.values():
            if w in syns or stem(w) in syns:
                out.extend(syns)
    return out


def rule_based_sql(question: str, schema: dict) -> dict:
    cols = schema["columns"]
    q = question.lower()
    words = keywords(q)
    measures = [c for c in cols if c["kind"] == "measure"]
    dims = [c for c in cols if c["kind"] in ("dimension", "identifier")]
    dates = [c for c in cols if c["kind"] == "date"]
    n = int(m.group(1)) if (m := re.search(r"\btop\s+(\d+)", q)) else 10
    measure = _match_col(_expand(words), measures, {"measure"}) or (measures[0] if measures else None)
    agg = "AVG" if re.search(r"\b(average|avg|mean)\b", q) else "COUNT" if re.search(r"\b(how many|count|number of)\b", q) and not measure else "SUM"
    dim_words = [w for w in words if not measure or stem(w) not in {stem(t) for t in re.split(r"[_\s]+", measure["name"].lower())}]
    dim = _match_col(_expand(dim_words), dims, {"dimension", "identifier"})
    mexpr = f'{agg}("{measure["name"]}")' if measure and agg != "COUNT" else "COUNT(*)"
    mlabel = f'{agg.lower()}_{measure["name"]}' if measure and agg != "COUNT" else "count"
    if re.search(r"\b(trend|monthly|per month|by month|over time|growth)\b", q) and dates:
        d = dates[0]["name"]
        if dim and re.search(r"\bgrowth\b", q):
            sql = (f'WITH m AS (SELECT "{dim["name"]}", date_trunc(\'month\', "{d}"::timestamp) AS month, {mexpr} AS value FROM data GROUP BY 1, 2) '
                   f'SELECT "{dim["name"]}", MIN(month) AS first_month, MAX(month) AS last_month, '
                   f'(MAX(value) FILTER (WHERE month = (SELECT MAX(month) FROM m)) - MAX(value) FILTER (WHERE month = (SELECT MIN(month) FROM m))) AS growth '
                   f'FROM m GROUP BY 1 ORDER BY growth DESC NULLS LAST')
            return {"sql": sql, "explanation": f"Change in {mlabel} between the first and last month, per {dim['name']}.", "chart": {"type": "bar", "x": dim["name"], "y": "growth"}}
        sql = f'SELECT date_trunc(\'month\', "{d}"::timestamp)::date AS month, {mexpr} AS {mlabel} FROM data GROUP BY 1 ORDER BY 1'
        return {"sql": sql, "explanation": f"Monthly {mlabel} using {d}.", "chart": {"type": "line", "x": "month", "y": mlabel}}
    if dim:
        order = "ASC" if re.search(r"\b(lowest|least|bottom|worst)\b", q) else "DESC"
        sql = f'SELECT "{dim["name"]}", {mexpr} AS {mlabel} FROM data GROUP BY 1 ORDER BY 2 {order} LIMIT {n}'
        return {"sql": sql, "explanation": f"{mlabel} grouped by {dim['name']}, {'top' if order == 'DESC' else 'bottom'} {n}.",
                "chart": {"type": "bar", "x": dim["name"], "y": mlabel}}
    if measure:
        sql = f'SELECT SUM("{measure["name"]}") AS total, AVG("{measure["name"]}") AS average, MIN("{measure["name"]}") AS min, MAX("{measure["name"]}") AS max, COUNT(*) AS rows FROM data'
        return {"sql": sql, "explanation": f"Summary statistics for {measure['name']}.", "chart": None}
    return {"sql": "SELECT * FROM data LIMIT 20", "explanation": "Showing a sample of rows (question not understood by the demo engine).", "chart": None}
