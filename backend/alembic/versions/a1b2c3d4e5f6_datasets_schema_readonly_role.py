"""datasets schema and read-only analytics role

Revision ID: a1b2c3d4e5f6
Revises: 7854cad9f5d6
"""
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "7854cad9f5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS datasets")
    # The read-only role is optional: hosted Postgres plans without CREATEROLE skip it instead of failing the deploy.
    op.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexora_readonly') THEN CREATE ROLE nexora_readonly NOLOGIN; END IF;
        GRANT USAGE ON SCHEMA datasets TO nexora_readonly;
        ALTER DEFAULT PRIVILEGES IN SCHEMA datasets GRANT SELECT ON TABLES TO nexora_readonly;
    EXCEPTION WHEN insufficient_privilege THEN RAISE NOTICE 'nexora_readonly role not created (insufficient privilege)';
    END $$;""")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS datasets CASCADE")
