"""Lightweight concurrent load test (no external tooling). Measures latency percentiles and error rate per endpoint.
Usage: backend/.venv/bin/python tests/performance/load_test.py --base http://localhost:8000 --concurrency 20 --requests 200
Logs in as the seeded demo owner. Rate limits are per-IP/org, so very high concurrency will (correctly) start returning 429s."""
import argparse
import asyncio
import json
import statistics
import time
import httpx


async def bench(client, name, method, url, n, conc, **kw):
    lat, errs, codes = [], 0, {}
    sem = asyncio.Semaphore(conc)

    async def one():
        nonlocal errs
        async with sem:
            t0 = time.perf_counter()
            try:
                r = await client.request(method, url, **kw)
                codes[r.status_code] = codes.get(r.status_code, 0) + 1
                if r.status_code >= 400:
                    errs += 1
            except Exception:
                errs += 1
            lat.append((time.perf_counter() - t0) * 1000)
    t0 = time.perf_counter()
    await asyncio.gather(*[one() for _ in range(n)])
    wall = time.perf_counter() - t0
    s = sorted(lat)
    return {"endpoint": name, "requests": n, "concurrency": conc, "rps": round(n / wall, 1), "p50_ms": round(statistics.median(s), 1),
            "p95_ms": round(s[int(0.95 * (len(s) - 1))], 1), "max_ms": round(s[-1], 1), "error_rate": round(errs / n, 3), "status_codes": codes}


async def main(base, conc, n):
    async with httpx.AsyncClient(base_url=base, timeout=30) as c:
        tok = (await c.post("/api/auth/login", json={"email": "demo.owner@example.com", "password": "DemoPassw0rd!"})).json()["access_token"]
        org = (await c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})).json()["organizations"][0]["id"]
        h = {"Authorization": f"Bearer {tok}", "X-Org-Id": org}
        ds = (await c.get("/api/datasets", headers=h)).json()[0]["id"]
        out = [
            await bench(c, "GET /api/health", "GET", "/api/health", n, conc),
            await bench(c, "GET /api/tasks", "GET", "/api/tasks", n, conc, headers=h),
            await bench(c, "POST /api/documents/search (hybrid RAG)", "POST", "/api/documents/search", n, conc, headers=h, json={"query": "who approves expenses above 5000 USD"}),
            await bench(c, "GET /api/analytics/dashboard", "GET", "/api/analytics/dashboard?days=30", max(20, n // 4), min(conc, 10), headers=h),
            await bench(c, "POST /api/datasets/{id}/sql (guarded SQL)", "POST", f"/api/datasets/{ds}/sql", max(20, n // 4), min(conc, 10), headers=h,
                        json={"sql": 'SELECT "customer", SUM("revenue") AS rev FROM data GROUP BY 1 ORDER BY 2 DESC'}),
        ]
    print(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--requests", type=int, default=200)
    a = ap.parse_args()
    res = asyncio.run(main(a.base, a.concurrency, a.requests))
    from pathlib import Path
    Path(__file__).with_name("results.json").write_text(json.dumps(res, indent=2))
