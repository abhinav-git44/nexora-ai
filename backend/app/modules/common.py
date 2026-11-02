import re
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.core.errors import bad_request


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def parse_uuid(value: str, what: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise bad_request(f"Invalid {what}")


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "org"
    return f"{s}-{uuid.uuid4().hex[:6]}"


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def user_brief(u) -> dict | None:
    if not u:
        return None
    return {"id": str(u.id), "email": u.email, "full_name": u.full_name, "avatar_url": u.avatar_url}
