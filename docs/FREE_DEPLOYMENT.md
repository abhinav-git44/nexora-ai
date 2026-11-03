# Free deployment (portfolio setup)

Run NEXORA AI live on free tiers. **Cost: $0.** No credit card is needed for Vercel, Render, Neon or Supabase at the time of writing
(Nov 2026) — free-tier terms change, so check each provider's pricing page.

| Part | Service (free tier) | Notes |
|---|---|---|
| Website | **Vercel Hobby** | Next.js; forwards `/api/*` to the API |
| API + background jobs | **Render Free** web service | 512 MB, sleeps after 15 idle minutes (~1 min to wake); free tier has no background workers, so jobs run inside the API (`RUN_WORKER_IN_PROCESS=true`) |
| Database | **Neon Free** Postgres + pgvector | 1 GB per project; suspends after 5 idle minutes (wakes in about a second) |
| File storage | **Supabase Free** Storage (S3-compatible) | ~1 GB; needed because Render's free disk is wiped on restart |
| Redis | not used | the app falls back to in-memory rate limiting on a single instance |
| Email | not used | verification/reset links are written to the Render logs (console email backend) |

## Trade-offs to know
* **Cold starts:** after 15 minutes without visitors the API sleeps; the next visit waits ~1 minute and the first request may time out —
  refresh once. Optional: a free uptime monitor (e.g. UptimeRobot, 5-minute interval) pinging `https://<your-vercel-app>/api/health` keeps
  it awake; one always-on service fits inside Render's 750 free hours/month.
* **Scheduled workflows** only fire while the API is awake.
* **Storage limits:** 1 GB database and ~1 GB files — plenty for a demo.

## Step 1 — Database (Neon)
1. Sign up at https://neon.com → **Create project** (region close to you, e.g. Singapore / AWS ap-southeast-1).
2. **SQL Editor** → run: `CREATE EXTENSION IF NOT EXISTS vector;`
3. **Dashboard → Connect** → copy the connection string (`postgresql://…neon.tech/neondb?sslmode=require`). This is `DATABASE_URL`.
   The app converts it to the right driver format automatically.

## Step 2 — File storage (Supabase)
1. Sign up at https://supabase.com → **New project** (any name; save the database password, though we don't use Supabase's database).
2. **Storage → New bucket** → name `nexora-uploads`, **private** (Public bucket OFF).
3. **Project Settings → Storage → S3 Connection**: enable the S3 protocol, note the **Endpoint** and **Region**, then
   **New access key** → copy the **Access key ID** and **Secret access key** (shown once).

## Step 3 — API (Render)
1. Sign up at https://render.com with GitHub → **New → Blueprint** → select the `nexora-ai` repository. Render reads `render.yaml`.
2. Fill in the prompted values:
   * `DATABASE_URL` — Neon string from step 1
   * `S3_ENDPOINT_URL`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` — from step 2
   * `APP_BASE_URL`, `API_BASE_URL` — put `https://placeholder.vercel.app` for now; you'll update them in step 5
   * `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` — optional (empty = labelled demo engine)
   `JWT_SECRET` and `ENCRYPTION_KEY` are generated automatically.
3. **Apply**. The first deploy builds the Docker image (~5–10 min), runs database migrations, and starts.
4. Open `https://nexora-api-xxxx.onrender.com/api/health` — you should see `"status":"ok"`. Copy this base URL.

## Step 4 — Website (Vercel)
1. Sign up at https://vercel.com with GitHub → **Add New → Project** → import `nexora-ai`.
2. **Root Directory:** `frontend` (Framework: Next.js is detected).
3. **Environment Variables:** `BACKEND_URL` = your Render URL from step 3 (no trailing slash), e.g. `https://nexora-api-xxxx.onrender.com`.
4. **Deploy**. Copy your site URL, e.g. `https://nexora-ai-abhinav.vercel.app`.

> `BACKEND_URL` is read at build time — if you change it, redeploy on Vercel.

## Step 5 — Connect the two
On Render → `nexora-api` → **Environment**: set `APP_BASE_URL` and `API_BASE_URL` to your Vercel URL → **Save** (Render redeploys).
These are used for links in emails, webhook and form URLs.

## Step 6 — Demo data (optional)
From your PC (Docker Desktop running), in the repository folder — PowerShell:
```powershell
docker run --rm -v "${PWD}\scripts:/scripts" `
  -e DATABASE_URL="<Neon connection string>" -e SUPER_ADMIN_EMAILS=admin@example.com -e APP_ENV=test `
  -e STORAGE_BACKEND=s3 -e S3_ENDPOINT_URL="<endpoint>" -e S3_REGION="<region>" -e S3_BUCKET=nexora-uploads `
  -e S3_ACCESS_KEY_ID="<key id>" -e S3_SECRET_ACCESS_KEY="<secret>" `
  nexora/backend python /scripts/seed_demo.py
```
(`nexora/backend` exists after you've run `scripts\start-windows.ps1` once.) Then sign in on your Vercel URL as
`demo.owner@example.com` / `DemoPassw0rd!`, or `admin@example.com` / `DemoPassw0rd!` for `/admin`.

Without seeding, just click **Start free** and create an account. Email verification links appear in Render → Logs.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Site loads but sign-in fails / "Request failed (500)" | API asleep or still deploying → open `<Render URL>/api/health`, wait for `ok`, retry |
| Render deploy fails at `alembic upgrade head` | Check `DATABASE_URL`; run `CREATE EXTENSION vector;` in Neon |
| Uploads stay "queued" | API restarted mid-job — jobs resume automatically when it wakes; or click Re-index |
| Uploads fail with storage errors | Re-check the S3 endpoint, region, keys and that the bucket name is `nexora-uploads` |
| Changed `BACKEND_URL` but site still calls the old API | Redeploy on Vercel (value is baked in at build) |
