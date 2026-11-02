"""Fixed-window rate limiting backed by Redis, with an in-process fallback for dev/tests."""
import time
import threading
import logging
from app.core.config import get_settings
from app.core.errors import AppError

log = logging.getLogger(__name__)
_local: dict[str, tuple[int, int]] = {}
_lock = threading.Lock()
_redis = None
_redis_checked = False
ENABLED = True  # tests switch this off except where rate limiting itself is under test


def _client():
    global _redis, _redis_checked
    if _redis_checked:
        return _redis
    _redis_checked = True
    url = get_settings().redis_url
    if not url:
        return None
    try:
        import redis
        r = redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
        r.ping()
        _redis = r
    except Exception as e:  # pragma: no cover
        log.warning("Redis unavailable, using in-memory rate limiter: %s", e)
        _redis = None
    return _redis


def hit(key: str, limit: int, window_s: int = 60) -> tuple[bool, int]:
    if not ENABLED:
        return True, 0
    window = int(time.time() // window_s)
    k = f"rl:{key}:{window}"
    r = _client()
    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.incr(k)
            pipe.expire(k, window_s + 5)
            count = pipe.execute()[0]
            return count <= limit, count
        except Exception:
            pass
    with _lock:
        w, c = _local.get(k, (window, 0))
        c += 1
        _local[k] = (window, c)
        if len(_local) > 50_000:
            _local.clear()
        return c <= limit, c


def enforce(key: str, limit: int, window_s: int = 60):
    ok, _ = hit(key, limit, window_s)
    if not ok:
        raise AppError(429, "rate_limited", "Too many requests. Please slow down.", {"retry_after_s": window_s})


def reset_local():
    _local.clear()
