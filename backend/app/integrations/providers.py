"""Integration catalogue and adapters. A connection is only marked 'connected' after a real, successful test call."""
import httpx
from app.core.crypto import decrypt_json
from app.core.netguard import assert_public_url

CATALOG = {
    "openai": {"name": "OpenAI", "category": "AI models", "auth": "api_key", "fields": [{"key": "api_key", "label": "API key", "secret": True}],
               "scopes": ["models.read", "responses.create"], "description": "Use your own OpenAI key for GPT models (BYOK).", "status": "available"},
    "anthropic": {"name": "Anthropic", "category": "AI models", "auth": "api_key", "fields": [{"key": "api_key", "label": "API key", "secret": True}],
                  "scopes": ["messages.create"], "description": "Use your own Anthropic key for Claude models (BYOK).", "status": "available"},
    "slack": {"name": "Slack", "category": "Communication", "auth": "webhook",
              "fields": [{"key": "webhook_url", "label": "Incoming webhook URL", "secret": True}], "scopes": ["incoming-webhook"],
              "description": "Post workflow alerts and agent results to a Slack channel.", "status": "available", "oauth": "slack"},
    "n8n": {"name": "n8n", "category": "Automation", "auth": "api_key",
            "fields": [{"key": "base_url", "label": "n8n base URL"}, {"key": "api_key", "label": "n8n API key", "secret": True}],
            "scopes": ["workflow:read", "webhook:call"], "description": "Call n8n workflows from NEXORA workflows and list your n8n automations.", "status": "available"},
    "webhooks": {"name": "Custom webhooks", "category": "Developer", "auth": "webhook",
                 "fields": [{"key": "url", "label": "Test endpoint URL"}], "scopes": ["post"],
                 "description": "Send signed JSON events to any HTTPS endpoint.", "status": "available"},
    "notion": {"name": "Notion", "category": "Knowledge", "auth": "api_key", "fields": [{"key": "api_key", "label": "Internal integration token", "secret": True}],
               "scopes": ["read_content"], "description": "Validate a Notion integration token (page import on roadmap).", "status": "beta"},
    "hubspot": {"name": "HubSpot", "category": "CRM", "auth": "api_key", "fields": [{"key": "api_key", "label": "Private app token", "secret": True}],
                "scopes": ["crm.objects.contacts.read"], "description": "Validate a HubSpot private app token (contact sync on roadmap).", "status": "beta"},
    "jira": {"name": "Jira", "category": "Project management", "auth": "api_key",
             "fields": [{"key": "site", "label": "Site (e.g. acme.atlassian.net)"}, {"key": "email", "label": "Account email"},
                        {"key": "api_key", "label": "API token", "secret": True}],
             "scopes": ["read:jira-work"], "description": "Validate Jira credentials (issue sync on roadmap).", "status": "beta"},
    "confluence": {"name": "Confluence", "category": "Knowledge", "auth": "api_key",
                   "fields": [{"key": "site", "label": "Site (e.g. acme.atlassian.net)"}, {"key": "email", "label": "Account email"},
                              {"key": "api_key", "label": "API token", "secret": True}],
                   "scopes": ["read:confluence-content.summary"], "description": "Validate Confluence credentials (space import on roadmap).", "status": "beta"},
    "google_workspace": {"name": "Google Workspace", "category": "Productivity", "auth": "oauth", "fields": [], "scopes": ["drive.readonly"],
                         "description": "OAuth connection to Google Drive (requires GOOGLE_CLIENT_ID).", "status": "requires_config", "oauth": "google"},
    "microsoft_365": {"name": "Microsoft 365", "category": "Productivity", "auth": "oauth", "fields": [], "scopes": ["Files.Read"],
                      "description": "Planned: OAuth via Microsoft Entra ID.", "status": "coming_soon"},
    "salesforce": {"name": "Salesforce", "category": "CRM", "auth": "oauth", "fields": [], "scopes": ["api"],
                   "description": "Planned: OAuth connected app.", "status": "coming_soon"},
    "cloudflare": {"name": "Cloudflare", "category": "Infrastructure", "auth": "api_key", "fields": [{"key": "api_key", "label": "API token", "secret": True}],
                   "scopes": ["user:read"], "description": "Validate a Cloudflare API token (used for R2 storage / deployments).", "status": "available"},
}


def test_connection(provider: str, creds: dict) -> tuple[bool, str]:
    """Performs a real, read-only call against the provider. Returns (ok, message)."""
    t = 10
    try:
        if provider == "openai":
            r = httpx.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {creds['api_key']}"}, timeout=t)
        elif provider == "anthropic":
            r = httpx.get("https://api.anthropic.com/v1/models", headers={"x-api-key": creds["api_key"], "anthropic-version": "2023-06-01"}, timeout=t)
        elif provider == "slack":
            url = assert_public_url(creds["webhook_url"])
            if not url.startswith("https://hooks.slack.com/"):
                return False, "Slack webhook URLs start with https://hooks.slack.com/"
            r = httpx.post(url, json={"text": "✅ NEXORA AI is connected to this channel."}, timeout=t)
        elif provider == "n8n":
            base = assert_public_url(creds["base_url"].rstrip("/"))
            r = httpx.get(f"{base}/api/v1/workflows?limit=1", headers={"X-N8N-API-KEY": creds["api_key"]}, timeout=t)
        elif provider == "webhooks":
            r = httpx.post(assert_public_url(creds["url"]), json={"event": "nexora.test", "ok": True}, timeout=t)
        elif provider == "notion":
            r = httpx.get("https://api.notion.com/v1/users/me", headers={"Authorization": f"Bearer {creds['api_key']}", "Notion-Version": "2022-06-28"}, timeout=t)
        elif provider == "hubspot":
            r = httpx.get("https://api.hubapi.com/crm/v3/objects/contacts?limit=1", headers={"Authorization": f"Bearer {creds['api_key']}"}, timeout=t)
        elif provider in ("jira", "confluence"):
            site = creds["site"].replace("https://", "").strip("/")
            path = "/rest/api/3/myself" if provider == "jira" else "/wiki/rest/api/user/current"
            r = httpx.get(assert_public_url(f"https://{site}{path}"), auth=(creds["email"], creds["api_key"]), timeout=t)
        elif provider == "cloudflare":
            r = httpx.get("https://api.cloudflare.com/client/v4/user/tokens/verify", headers={"Authorization": f"Bearer {creds['api_key']}"}, timeout=t)
        else:
            return False, "This integration cannot be tested yet"
    except KeyError as e:
        return False, f"Missing field {e}"
    except httpx.HTTPError as e:
        return False, f"Connection failed: {e.__class__.__name__}"
    except Exception as e:
        return False, str(getattr(e, "detail", None) or e)
    if 200 <= r.status_code < 300:
        return True, "Connection verified"
    return False, f"Provider responded with HTTP {r.status_code}"


def n8n_call_webhook(conn, path: str, body: dict) -> dict:
    creds = decrypt_json(conn.encrypted_credentials)
    base = assert_public_url(creds["base_url"].rstrip("/"))
    r = httpx.post(f"{base}/webhook/{path.strip('/')}", json=body, headers={"X-N8N-API-KEY": creds.get("api_key", "")}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"n8n webhook returned HTTP {r.status_code}")
    try:
        return {"status_code": r.status_code, "response": r.json()}
    except ValueError:
        return {"status_code": r.status_code, "response": r.text[:2000]}


def n8n_list_workflows(conn) -> list[dict]:
    creds = decrypt_json(conn.encrypted_credentials)
    base = assert_public_url(creds["base_url"].rstrip("/"))
    r = httpx.get(f"{base}/api/v1/workflows?limit=50", headers={"X-N8N-API-KEY": creds["api_key"]}, timeout=15)
    r.raise_for_status()
    return [{"id": w["id"], "name": w["name"], "active": w.get("active")} for w in r.json().get("data", [])]
