"""Encryption at rest for third-party credentials (Fernet / AES-128-CBC + HMAC)."""
import base64
import hashlib
import json
from cryptography.fernet import Fernet
from app.core.config import get_settings


def _fernet() -> Fernet:
    s = get_settings()
    key = s.encryption_key
    if not key:
        if s.is_prod:
            raise RuntimeError("ENCRYPTION_KEY is required in production")
        # Dev fallback: derive from JWT secret so local data stays decryptable between restarts.
        key = base64.urlsafe_b64encode(hashlib.sha256(s.jwt_secret.encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt_json(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token: str) -> dict:
    return json.loads(_fernet().decrypt(token.encode()))


def encrypt_str(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_str(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def mask(value: str) -> str:
    return value[:3] + "…" + value[-4:] if len(value) > 10 else "••••"
