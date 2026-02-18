"""Rate limit dependency for public endpoints (FastAPI Limiter–style, Redis-backed)."""

from fastapi import Request
from fastapi.exceptions import HTTPException

from app.constants.limits import (
    RATE_LIMIT_PUBLIC_REQUESTS,
    RATE_LIMIT_PUBLIC_WINDOW_SEC,
)
from app.constants.messages import RATE_LIMIT_KEY_PREFIX
from app.utils.redis_client import redis_client


def get_client_identifier(request: Request) -> str:
    """Client identifier for rate limiting: X-Forwarded-For (first hop) or client host."""
    # Prefer X-Forwarded-For when behind a proxy so we limit by real client IP, not proxy.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


async def rate_limit_public(request: Request) -> None:
    """
    Dependency for public endpoints. Uses Redis fixed-window rate limit per client (IP).
    Raises 429 Too Many Requests if limit exceeded; otherwise returns None (request allowed).
    """
    client_id = get_client_identifier(request)
    key = f"{RATE_LIMIT_KEY_PREFIX}:{client_id}"
    # Fixed window: INCR key, set TTL on first hit; allowed iff count <= max_requests.
    allowed = await redis_client.rate_limit_check(
        key,
        window_sec=RATE_LIMIT_PUBLIC_WINDOW_SEC,
        max_requests=RATE_LIMIT_PUBLIC_REQUESTS,
    )
    if not allowed:
        # 429 is handled by http_exception_handler → unified { success: false, error }.
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
        )
