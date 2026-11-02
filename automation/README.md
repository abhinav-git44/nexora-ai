# Automation

NEXORA owns workflow **definitions, versions, permissions and execution records** (see `backend/app/workflows`). n8n is used where its
connector library adds value, in two directions:

| Direction | How | Asset |
|---|---|---|
| NEXORA → n8n | The **Run n8n workflow** node POSTs to `{N8N_BASE_URL}/webhook/<path>` using the org's encrypted n8n connection | `n8n/lead-enrichment.workflow.json` |
| n8n → NEXORA | n8n calls a NEXORA **Webhook trigger** URL with an `X-Nexora-Signature: sha256=<hmac>` header | `n8n/nexora-webhook-trigger.workflow.json` |

Run n8n locally: `docker compose -f deployment/docker-compose.yml --profile automation up n8n`, import the JSON files, then connect
n8n in **Integrations** (base URL + API key). The connection is only marked connected after a real `GET /api/v1/workflows` succeeds.

Built-in node catalogue (`GET /api/workflows/nodes`): triggers (manual, schedule, webhook, form, document uploaded), actions (email,
AI generate, summarise document, extract data, create task, upsert record, webhook, n8n, generate report) and logic (if/else, filter,
branch, delay, loop, approval). Starter recipes live in `backend/app/workflows/templates.py`.
