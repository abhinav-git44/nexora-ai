"""analytics schema views for SQL / Power BI

Revision ID: b7c8d9e0f1a2
Revises: 17538ecaf141
"""
from pathlib import Path
from alembic import op

revision = "b7c8d9e0f1a2"
down_revision = "17538ecaf141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute((Path(__file__).resolve().parents[2] / "app" / "sql" / "analytics_views.sql").read_text())
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexora_readonly') THEN
            GRANT USAGE ON SCHEMA analytics TO nexora_readonly;
            GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO nexora_readonly;
        END IF;
    EXCEPTION WHEN insufficient_privilege THEN RAISE NOTICE 'analytics grants skipped (insufficient privilege)';
    END $$;""")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS analytics CASCADE")
