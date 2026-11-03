"""Central configuration. All secrets come from the environment; nothing is hardcoded."""
from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"  # development | test | production
    app_name: str = "NEXORA AI"
    app_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"

    database_url: str = "postgresql+psycopg://nexora:nexora@localhost:5432/nexora"
    # Read-only role used for executing LLM-generated SQL. Falls back to main URL in dev.
    analytics_readonly_database_url: str | None = None
    redis_url: str | None = "redis://localhost:6379/0"

    jwt_secret: str = "dev-only-change-me-dev-only-change-me"
    jwt_access_ttl_minutes: int = 15
    refresh_ttl_days: int = 14
    # Fernet key (urlsafe base64, 32 bytes) for encrypting integration credentials at rest.
    encryption_key: str | None = None

    cookie_secure: bool = False

    # AI providers
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    ai_default_provider: str = "auto"  # auto | anthropic | openai | demo
    ai_request_timeout_s: float = 60.0
    ai_max_retries: int = 2
    anthropic_refusal_fallback: bool = True
    model_catalog_path: str | None = None  # optional JSON override of the model catalog
    embedding_provider: str = "auto"  # auto | openai | local

    # Storage
    storage_backend: str = "local"  # local | r2 | s3 (any S3-compatible service, e.g. Supabase Storage)
    storage_local_dir: str = "./var/uploads"
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    max_upload_mb: int = 20

    # Email
    email_backend: str = "console"  # console | smtp | resend
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    email_from: str = "NEXORA AI <no-reply@nexora.local>"
    resend_api_key: str | None = None

    # Billing
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_starter: str | None = None
    stripe_price_professional: str | None = None
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None

    # OAuth
    google_client_id: str | None = None
    google_client_secret: str | None = None
    slack_client_id: str | None = None
    slack_client_secret: str | None = None

    # Analytics
    mixpanel_token: str | None = None

    # n8n
    n8n_base_url: str | None = None
    n8n_api_key: str | None = None

    # Limits
    rate_limit_per_minute: int = 120
    ai_rate_limit_per_minute: int = 30
    run_worker_in_process: bool = True
    super_admin_emails: str = ""  # comma-separated; bootstrap super admins

    @field_validator("database_url", "analytics_readonly_database_url", mode="before")
    @classmethod
    def _normalise_db_url(cls, v):
        """Hosted providers (Neon, Render, Supabase) hand out postgres:// or postgresql:// URLs; use the psycopg 3 driver."""
        if isinstance(v, str):
            for prefix in ("postgres://", "postgresql://"):
                if v.startswith(prefix):
                    return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def is_prod(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_prod and s.jwt_secret.startswith("dev-only"):
        raise RuntimeError("JWT_SECRET must be set in production")
    return s
