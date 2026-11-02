from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class AppError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        super().__init__(status_code=status_code, detail={"code": code, "message": message, "details": details or {}})


def not_found(what: str = "Resource") -> AppError:
    # Same response for "doesn't exist" and "belongs to another tenant" to avoid ID enumeration.
    return AppError(404, "not_found", f"{what} not found")


def forbidden(message: str = "You do not have permission to perform this action") -> AppError:
    return AppError(403, "forbidden", message)


def bad_request(message: str, code: str = "bad_request", details: dict | None = None) -> AppError:
    return AppError(400, code, message, details)


def plan_limit(message: str, details: dict | None = None) -> AppError:
    return AppError(402, "plan_limit_reached", message, details)


async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if not isinstance(detail, dict):
        detail = {"code": "error", "message": str(detail), "details": {}}
    return JSONResponse(status_code=exc.status_code, content={"error": detail}, headers=getattr(exc, "headers", None))
