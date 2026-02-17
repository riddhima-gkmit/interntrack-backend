"""Map SQLAlchemy/PostgreSQL IntegrityError to user-friendly messages (unique, not null, FK, check)."""

import re

from sqlalchemy.exc import IntegrityError

def extract_pg_error(exc: IntegrityError) -> str:
    """
    Map PostgreSQL IntegrityError to a user-facing message.
    Works with SQLAlchemy + asyncpg (unique, not null, foreign key, check).
    """
    # exc.orig is the underlying DB driver exception (e.g. asyncpg) with the real error text.
    text = str(exc.orig) if hasattr(exc, "orig") else str(exc)

    # Unique constraint / duplicate key (e.g. duplicate email, username).
    if "duplicate key value" in text or "UniqueViolationError" in text:
        m = re.search(r"Key \((.+?)\)=\((.+?)\)", text)
        if m:
            col, val = m.groups()
            return f"{col.capitalize()} '{val}' already exists."
        return "Value already exists."

    # Not null violation: required column was null.
    if "NotNullViolationError" in text or "null value in column" in text:
        m = re.search(r'null value in column "(.+?)"', text, re.IGNORECASE)
        if m:
            return f"Field '{m.group(1)}' cannot be null."
        return "A required field is missing."

    # Foreign key violation: referenced row does not exist (e.g. invalid user_id, tenant_id).
    if "ForeignKeyViolationError" in text or "violates foreign key constraint" in text:
        m = re.search(r"Key \((.+?)\)=\((.+?)\)", text)
        if m:
            col, val = m.groups()
            return f"Related {col} '{val}' does not exist."
        return "Foreign key constraint violated."

    # Check constraint: custom DB check failed.
    if "CheckViolationError" in text or "check constraint" in text:
        return "Data did not meet required constraints."

    # Unknown constraint type: return raw message (caller will show as 400).
    return text
