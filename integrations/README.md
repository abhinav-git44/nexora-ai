# Integrations

Catalogue: `backend/app/integrations/providers.py` (snapshot `catalog.json`). Status semantics:

- `available` — credential form + **real read-only test call**; only a successful call marks the connection `connected`.
- `beta` — connection validation implemented; data sync is on the roadmap (PRODUCT_ROADMAP V1).
- `requires_config` — OAuth flow implemented, needs server OAuth client credentials (e.g. `GOOGLE_CLIENT_ID`).
- `coming_soon` — listed for discovery; not connectable.

Credentials are Fernet-encrypted at rest (`ENCRYPTION_KEY`), masked in API responses, destroyed on disconnect, and every
connect/test/disconnect is written to `integration_logs` and the audit log.
