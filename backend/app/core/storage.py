"""Object storage abstraction. Keys are always prefixed by org id so files are tenant-partitioned."""
import os
import uuid
from pathlib import Path
from app.core.config import get_settings


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root)):
            raise ValueError("invalid storage key")
        return p

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream"):
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str):
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass


class S3Storage:
    """Any S3-compatible object store: Cloudflare R2, Supabase Storage, AWS S3, MinIO."""
    def __init__(self, endpoint_url: str | None, bucket: str, access_key: str, secret_key: str, region: str):
        import boto3
        from botocore.config import Config
        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint_url, aws_access_key_id=access_key, aws_secret_access_key=secret_key,
                                   region_name=region, config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))

    def put(self, key, data, content_type="application/octet-stream"):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)


_storage = None


def get_storage():
    global _storage
    if _storage is None:
        s = get_settings()
        if s.storage_backend == "r2" and s.r2_bucket:
            _storage = S3Storage(f"https://{s.r2_account_id}.r2.cloudflarestorage.com", s.r2_bucket, s.r2_access_key_id, s.r2_secret_access_key, "auto")
        elif s.storage_backend == "s3" and s.s3_bucket:
            _storage = S3Storage(s.s3_endpoint_url, s.s3_bucket, s.s3_access_key_id, s.s3_secret_access_key, s.s3_region)
        else:
            _storage = LocalStorage(s.storage_local_dir)
    return _storage


def make_key(org_id, kind: str, filename: str) -> str:
    safe = "".join(c for c in filename if c.isalnum() or c in "._-")[-120:] or "file"
    return f"orgs/{org_id}/{kind}/{uuid.uuid4().hex}_{safe}"
