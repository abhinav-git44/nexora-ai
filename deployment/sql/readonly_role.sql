-- Login role for (a) executing LLM-generated SQL and (b) Power BI / BI tools. SELECT-only on the datasets schema
-- and on the analytics views. Point ANALYTICS_READONLY_DATABASE_URL at this role in production.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexora_bi') THEN
    CREATE ROLE nexora_bi LOGIN PASSWORD 'change-me' IN ROLE nexora_readonly;
  END IF;
END $$;
ALTER ROLE nexora_bi SET default_transaction_read_only = on;
ALTER ROLE nexora_bi SET statement_timeout = '15s';
GRANT USAGE ON SCHEMA datasets, analytics TO nexora_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA datasets, analytics TO nexora_readonly;
