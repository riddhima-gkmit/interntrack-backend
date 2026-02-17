"""Invitation CRUD: get by token or email+tenant, create (unique token), mark accepted. Powers invite flow; service sends email with link containing token."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import InvitationRole
from app.models import Invitation


def _default_expires_at() -> datetime:
    """Default invitation expiry when caller does not pass expires_at (e.g. 7 days)."""
    return datetime.now(UTC) + timedelta(days=7)


async def get_invitation_by_token(
    db: AsyncSession, token: str, include_deleted: bool = False
) -> Invitation | None:
    """Get invitation by token (from link). Excludes soft-deleted and expired unless include_deleted; expiry checked in Python after fetch."""
    q = select(Invitation).where(Invitation.token == token)
    if not include_deleted:
        q = q.where(Invitation.deleted_at.is_(None))
    result = await db.execute(q)
    inv = result.scalar_one_or_none()
    if (
        inv
        and not include_deleted
        and inv.expires_at
        and inv.expires_at < datetime.now(UTC)
    ):
        return None
    return inv


async def get_invitation_by_email_tenant(
    db: AsyncSession, email: str, tenant_id: UUID, include_deleted: bool = False
) -> Invitation | None:
    """Pending invitation by email + tenant for duplicate check: only non-accepted, not expired; email normalized to lower/strip."""
    q = select(Invitation).where(
        Invitation.email == email.lower().strip(),
        Invitation.tenant_id == tenant_id,
        Invitation.accepted_at.is_(None),
    )
    if not include_deleted:
        q = q.where(Invitation.deleted_at.is_(None))
    q = q.where(Invitation.expires_at > datetime.now(UTC))
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def create_invitation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    created_by_id: UUID,
    email: str,
    role: InvitationRole,
    expires_at: datetime | None = None,
) -> Invitation:
    """Create invitation with a cryptographically secure url-safe token; email stored lowercased and stripped."""
    token = secrets.token_urlsafe(32)
    if expires_at is None:
        expires_at = _default_expires_at()
    inv = Invitation(
        tenant_id=tenant_id,
        created_by_id=created_by_id,
        email=email.lower().strip(),
        role=role,
        token=token,
        expires_at=expires_at,
    )
    db.add(inv)
    await db.flush()
    await db.refresh(inv)
    return inv


async def mark_accepted(db: AsyncSession, invitation_id: UUID) -> bool:
    """Set accepted_at to now (used after user completes signup/accept). Excludes soft-deleted; returns True if invitation existed."""
    result = await db.execute(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.deleted_at.is_(None),
        )
    )
    inv = result.scalar_one_or_none()
    if not inv:
        return False
    inv.accepted_at = datetime.now(UTC)
    await db.flush()
    return True
