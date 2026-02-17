"""Password hashing and verification utilities (bcrypt; passwords truncated to 72 bytes)."""

import bcrypt

from app.constants import BCRYPT_MAX_PASSWORD_BYTES

def hash_password(password: str) -> str:
    """Hash a password using bcrypt (truncated to bcrypt's 72-byte limit)."""
    # Truncate to 72 bytes so hash is deterministic; bcrypt ignores bytes beyond that anyway.
    password_bytes = password.encode("utf-8")[:BCRYPT_MAX_PASSWORD_BYTES]
    salt = bcrypt.gensalt()  # New salt per password for uniqueness.
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")  # Store as string in DB (includes algorithm + salt + hash).


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash (constant-time comparison via bcrypt)."""
    # Same truncation as hash_password so verification matches.
    password_bytes = plain_password.encode("utf-8")[:BCRYPT_MAX_PASSWORD_BYTES]
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)
