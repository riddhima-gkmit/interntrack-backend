"""Application constants."""

# Bcrypt truncates at 72 bytes; truncate explicitly to avoid backend errors.
BCRYPT_MAX_PASSWORD_BYTES = 72
