"""Global exception handlers: DB errors, HTTP, validation, and unhandled → unified { success: false, error: { code, message } }."""

import logging

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.constants.messages import INTERNAL_ERROR
from app.utils.db_errors import extract_pg_error

logger = logging.getLogger(__name__)

# Used in error_response() to set error.code from status code.
STATUS_TO_ERROR_CODE = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
    status.HTTP_429_TOO_MANY_REQUESTS: "TOO_MANY_REQUESTS",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_ERROR",
}


def error_response(
    status_code: int,
    message: str,
    code: str | None = None,
    details: list | dict | None = None,
) -> JSONResponse:
    """Return unified error format: { success: false, error: { code, message [, details] } }."""
    # If code not provided, map status code to string (e.g. 404 → "NOT_FOUND").
    error_code = code or STATUS_TO_ERROR_CODE.get(status_code, "ERROR")
    body: dict = {
        "success": False,
        "error": {
            "code": error_code,
            "message": message,
        },
    }
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


async def db_exception_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """Map database constraint errors (unique, FK, not null, check) to unified 400 response."""
    message = extract_pg_error(exc)
    return error_response(
        status.HTTP_400_BAD_REQUEST,
        message,
        code="INTEGRITY_ERROR",
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Forward HTTP exceptions (raise HTTPException in code) in unified error format."""
    detail = exc.detail
    # FastAPI/Starlette can pass detail as dict, list (e.g. validation-style), or string.
    if isinstance(detail, dict):
        message = detail.get("message", detail.get("detail", str(detail)))
    elif isinstance(detail, list):
        message = detail[0] if detail else "Request failed"
        if isinstance(message, dict):
            message = message.get("msg", message.get("message", str(message)))
    else:
        message = str(detail) if detail else "Request failed"
    code = STATUS_TO_ERROR_CODE.get(exc.status_code, "HTTP_ERROR")
    return error_response(exc.status_code, message, code=code)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Format Pydantic/request validation errors. Top-level message is summary; field-level in details."""
    errors = []
    for error in exc.errors():
        # loc is e.g. ("body", "email"); skip "body" so field is "email" or "items.0.name".
        field = ".".join(str(x) for x in error["loc"] if x != "body")
        msg = error.get("msg", "Invalid value")
        errors.append({"field": field, "message": msg})
    message = "Validation failed."
    return error_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        message,
        code="VALIDATION_ERROR",
        details=errors,
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log full traceback and return generic 500. Never expose internal details to client."""
    logger.exception("Unhandled exception: %s", exc)
    return error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        INTERNAL_ERROR,
        code="INTERNAL_ERROR",
    )
