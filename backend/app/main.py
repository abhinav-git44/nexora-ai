import logging
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text
from app.core.config import get_settings
from app.core.db import engine
from app.core.errors import http_exception_handler, AppError
from app.core import ratelimit

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("nexora")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import app.worker.tasks  # noqa: F401  register job handlers
    if settings.run_worker_in_process and settings.app_env != "test":
        from app.worker.queue import start_background
        start_background()
        log.info("In-process worker started")
    yield
    from app.worker.queue import stop_background
    stop_background()


app = FastAPI(title="NEXORA AI API", version="1.0.0", lifespan=lifespan,
              description="Business operations & workflow intelligence platform. All tenant endpoints require `Authorization: Bearer` and `X-Org-Id`.")

app.add_middleware(CORSMiddleware, allow_origins=[settings.app_base_url], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    t0 = time.perf_counter()
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/health"):
        ip = request.client.host if request.client else "x"
        ok, _ = ratelimit.hit(f"global:{ip}", settings.rate_limit_per_minute * 5)
        if not ok:
            return JSONResponse(status_code=429, content={"error": {"code": "rate_limited", "message": "Too many requests", "details": {}}})
    try:
        response = await call_next(request)
    except Exception:
        log.exception("Unhandled error rid=%s path=%s", rid, path)
        response = JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Something went wrong. Reference: " + rid, "details": {}}})
    ms = int((time.perf_counter() - t0) * 1000)
    response.headers["X-Request-Id"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.is_prod:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    if path.startswith("/api/"):
        log.info("rid=%s %s %s %s %dms", rid, request.method, path, response.status_code, ms)
    return response


app.add_exception_handler(AppError, http_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errs = [{"field": ".".join(str(x) for x in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": errs[0]["message"] if errs else "Invalid input",
                                                            "details": {"fields": errs}}})


@app.get("/api/health", tags=["system"])
def health():
    db_ok = True
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
    except Exception:
        db_ok = False
    from app.ai.gateway import provider_status
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "ai": provider_status(), "version": app.version}


from app.modules import auth, orgs, notifications  # noqa: E402
for r in (auth.router, orgs.router, orgs.invitations_router, notifications.router):
    app.include_router(r)

from app.modules import registry  # noqa: E402
for r in registry.routers():
    app.include_router(r)
