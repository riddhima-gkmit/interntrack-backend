"""Middleware: log every request (method, path, status, duration) and attach a short request_id to request.state."""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log each request: method, path, status code, duration. Attach request_id (first 8 chars of UUID) to state."""

    async def dispatch(self, request: Request, call_next):
        # Short id to correlate this request in logs; set before call_next so handlers can use request.state.request_id.
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        # Log after request completes so we have status code and total duration.
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
