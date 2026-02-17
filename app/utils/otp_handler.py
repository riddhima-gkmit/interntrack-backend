"""OTP generation, Redis storage (hashed), send/verify with rate limits and cooldown."""

import asyncio
import hashlib
import hmac
import secrets

from uuid import UUID
from fastapi import BackgroundTasks, HTTPException, status
from app.constants.auth_ttl import OTP_COOLDOWN, OTP_TTL
from app.constants.limits import OTP_MAX_ATTEMPTS, OTP_MAX_SENDS
from app.constants.messages import OTP_INVALID, OTP_RATE_LIMITED, OTP_SENT
from app.utils.redis_client import redis_client


def otp_cooldown_message(remaining_seconds: int) -> str:
    """Build cooldown message with wait time in minutes (round up so user sees at least 1 minute)."""
    # (remaining_seconds + 59) // 60 rounds up to whole minutes; max(1, ...) avoids "0 minutes".
    wait_minutes = max(1, (remaining_seconds + 59) // 60)
    return f"Please wait {wait_minutes} minute(s) before requesting another OTP."


def _otp_key(email: str, otp_type: str, tenant_id: UUID | None) -> str:
    """Redis key for stored OTP hash. Prefix by tenant so OTPs are isolated per tenant (e.g. verify_email for tenant A vs B)."""
    prefix = f"tenant:{tenant_id}:" if tenant_id else "tenant:none:"
    return f"{prefix}otp:{otp_type}:{email}"


def _attempt_key(email: str, otp_type: str, tenant_id: UUID | None) -> str:
    """Redis key for failed verify attempts; used to lock out after OTP_MAX_ATTEMPTS."""
    prefix = f"tenant:{tenant_id}:" if tenant_id else "tenant:none:"
    return f"{prefix}otp_attempts:{otp_type}:{email}"


def _cooldown_key(email: str, otp_type: str, tenant_id: UUID | None) -> str:
    """Redis key for send cooldown; set after OTP_MAX_SENDS to block further sends for OTP_COOLDOWN seconds."""
    prefix = f"tenant:{tenant_id}:" if tenant_id else "tenant:none:"
    return f"{prefix}otp_cooldown:{otp_type}:{email}"


def _send_count_key(email: str, otp_type: str, tenant_id: UUID | None) -> str:
    """Redis key for number of OTPs sent in current window; when it reaches OTP_MAX_SENDS we start cooldown."""
    prefix = f"tenant:{tenant_id}:" if tenant_id else "tenant:none:"
    return f"{prefix}otp_send_count:{otp_type}:{email}"


async def send_otp(
    email: str,
    otp_type: str,
    tenant_id: UUID | None,
    send_fn,
    *,
    subject: str = "Your OTP",
    body_template: str = "Your OTP is: {otp}. It expires in {minutes} minutes.",
    background_tasks: BackgroundTasks | None = None,
) -> str:
    """Generate OTP, store hashed in Redis, call send_fn(email, subject, body). Returns success message.
    Allows OTP_MAX_SENDS (3) sends per email before cooldown; then 429 with wait time.
    If background_tasks is provided, email is sent in the background."""
    cooldown_k = _cooldown_key(email, otp_type, tenant_id)
    send_count_k = _send_count_key(email, otp_type, tenant_id)

    # If already in cooldown (after OTP_MAX_SENDS), return 429 with remaining wait time.
    if await redis_client.get(cooldown_k):
        ttl = await redis_client.ttl(cooldown_k)
        wait_seconds = ttl if ttl > 0 else OTP_COOLDOWN
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=otp_cooldown_message(wait_seconds),
        )

    # Check how many times we've already sent in this window
    count_val = await redis_client.get(send_count_k)
    send_count = int(count_val) if count_val else 0
    if send_count >= OTP_MAX_SENDS:
        # 4th (or more) attempt: start cooldown, reset send count, return 429
        await redis_client.set(cooldown_k, "1", expire=OTP_COOLDOWN)
        await redis_client.delete(send_count_k)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=otp_cooldown_message(OTP_COOLDOWN),
        )

    otp = "".join(str(secrets.randbelow(10)) for _ in range(6))
    # Store hash only so Redis compromise does not expose plain OTP.
    hashed = hashlib.sha256(otp.encode()).hexdigest()
    otp_k = _otp_key(email, otp_type, tenant_id)
    attempt_k = _attempt_key(email, otp_type, tenant_id)
    await redis_client.set(otp_k, hashed, expire=OTP_TTL)
    await redis_client.set(attempt_k, "0", expire=OTP_TTL)  # Reset failed-verify count for this OTP.
    await redis_client.set(send_count_k, str(send_count + 1), expire=OTP_COOLDOWN)
    body = body_template.format(otp=otp, minutes=OTP_TTL // 60)
    if background_tasks:
        background_tasks.add_task(send_fn, email, subject, body)
    else:
        await send_fn(email, subject, body)
    return OTP_SENT


async def verify_otp(
    email: str, otp: str, otp_type: str, tenant_id: UUID | None
) -> bool:
    """Verify OTP. Raises HTTPException on invalid/expired or too many attempts. Deletes OTP on success."""
    otp_k = _otp_key(email, otp_type, tenant_id)
    attempt_k = _attempt_key(email, otp_type, tenant_id)
    cooldown_k = _cooldown_key(email, otp_type, tenant_id)
    stored = await redis_client.get(otp_k)
    if not stored:
        # OTP expired or never set; same message to avoid leaking validity.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=OTP_INVALID,
        )
    attempts_val = await redis_client.get(attempt_k)
    if attempts_val and int(attempts_val) >= OTP_MAX_ATTEMPTS:
        # Too many wrong attempts: clear OTP and lock out with 429.
        await redis_client.delete(otp_k, attempt_k, cooldown_k)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=OTP_RATE_LIMITED,
        )
    hashed_input = hashlib.sha256(otp.encode()).hexdigest()
    if not hmac.compare_digest(stored, hashed_input):
        await redis_client.incr(attempt_k)
        await asyncio.sleep(0.5)  # Throttle brute-force attempts.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=OTP_INVALID,
        )
    # Success: delete OTP and attempt counter so they cannot be reused.
    await redis_client.delete(otp_k, attempt_k, cooldown_k)
    return True
