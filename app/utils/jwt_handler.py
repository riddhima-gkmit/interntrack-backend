"""JWT creation for access and refresh tokens. Payload includes sub, type, and (for access) role and tenant_id."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4
from jose import jwt
from app.config import settings

def create_access_token(user) -> str:
    """Build access token with user id, role, and tenant_id for permission and scoping."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),  # Subject: user id; used by get_current_user to load user.
        "jti": str(uuid4()),  # Unique token id; can be used for revocation/blacklist if needed.
        "type": "access",  # So dependencies reject refresh tokens when access is required.
        "role": user.role.value,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,  # None for SUPER_ADMIN.
        "iat": now,  # Issued at (standard claim).
        "exp": now + timedelta(minutes=settings.ACCESS_EXPIRE_MIN),  # Expiry; verified on decode.
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user) -> str:
    """Build refresh token (sub + jti only); jti is used for blacklisting on logout/refresh."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),  # Identify user when exchanging refresh for new access token.
        "jti": str(uuid4()),  # Required: we blacklist this JTI on logout and after refresh.
        "type": "refresh",  # So only /auth/refresh accepts this; API routes require access token.
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
