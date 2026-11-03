"""Compatibility with free/managed hosting: Neon URLs, platform-generated secrets, S3-compatible storage, no CREATEROLE."""
import uuid
import pytest
from tests.conftest import set_plan
from tests.fixtures import SALES_CSV


@pytest.mark.parametrize("raw", ["postgres://u:p@h:5432/db?sslmode=require", "postgresql://u:p@h:5432/db?sslmode=require"])
def test_database_url_normalised(raw):
    from app.core.config import Settings
    s = Settings(database_url=raw)
    assert s.database_url == "postgresql+psycopg://u:p@h:5432/db?sslmode=require"
    assert Settings(database_url="postgresql+psycopg://x/y").database_url == "postgresql+psycopg://x/y"


def test_non_fernet_encryption_key_is_accepted(monkeypatch):
    from app.core import crypto
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "encryption_key", "Render+generated/value==")
    token = crypto.encrypt_json({"api_key": "secret"})
    assert crypto.decrypt_json(token) == {"api_key": "secret"} and "secret" not in token


def test_s3_compatible_storage_roundtrip():
    moto = pytest.importorskip("moto")
    import boto3
    from app.core.storage import S3Storage
    with moto.mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="nexora")
        st = S3Storage(None, "nexora", "test", "test", "us-east-1")
        st.put("orgs/1/documents/a.txt", b"hello", "text/plain")
        assert st.get("orgs/1/documents/a.txt") == b"hello"
        st.delete("orgs/1/documents/a.txt")


def test_dataset_upload_survives_failed_grant(client, owner, monkeypatch):
    """On hosts where the optional read-only role cannot exist, the GRANT fails inside a savepoint and the upload still succeeds."""
    set_plan(owner.org_id, "professional")
    from app.data import service
    real_text = service.text
    missing = f"role_missing_{uuid.uuid4().hex[:6]}"
    monkeypatch.setattr(service, "text", lambda sql: real_text(sql.replace("TO nexora_readonly", f"TO {missing}")))
    r = owner.post("/api/datasets", files={"file": ("sales.csv", SALES_CSV.encode(), "text/csv")})
    assert r.status_code == 201, r.text
    q = owner.post(f"/api/datasets/{r.json()['id']}/query", json={"question": "total revenue by region"}).json()
    assert q["status"] == "succeeded"
