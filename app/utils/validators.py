"""Shared validation helpers used by auth, user, and tenant schemas. Raise ValueError for Pydantic to surface as 422."""


def password_strength(value: str) -> str:
    """Validate password length (min 8 characters)."""
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters")
    return value


def first_name_not_empty(v: str) -> str:
    """Validate first name is non-empty after strip."""
    if not v or not v.strip():
        raise ValueError("First name must be at least 1 character")
    return v.strip()
