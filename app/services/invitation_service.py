"""Invitation service: create invite (send email), get by token, accept (create user + mark accepted). Role (INTERN/MENTOR) enforced in router."""

from uuid import UUID

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.crud import invitation_crud, user_crud
from app.enums import UserRole
from app.schemas.invitation import InvitationCreateSchema
from app.services.email_service import email_service
from app.utils.otp_handler import send_otp
from app.utils.password import hash_password
from app.utils.response_helpers import success_response


async def create_invitation(
    db: AsyncSession,
    data: InvitationCreateSchema,
    tenant_id: UUID,
    created_by_id: UUID,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """Create invitation and send email. Reject if pending invite or existing user with same email in tenant."""
    existing = await invitation_crud.get_invitation_by_email_tenant(
        db, data.email, tenant_id
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation already sent to this email for this organization",
        )
    existing_user = await user_crud.get_user_by_email_ci(db, data.email, tenant_id)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists in this organization",
        )
    inv = await invitation_crud.create_invitation(
        db,
        tenant_id=tenant_id,
        created_by_id=created_by_id,
        email=data.email,
        role=data.role,
    )
    await db.commit()
    await db.refresh(inv)

    # Fallback to query-string only if FRONTEND_URL not set (e.g. dev).
    invite_url = (
        f"{settings.FRONTEND_URL}/register?tenant_id={tenant_id}&token={inv.token}"
    )
    if not settings.FRONTEND_URL:
        invite_url = f"tenant_id={tenant_id}&token={inv.token}"
    body = f"You have been invited to join. Complete your registration at: {invite_url}"
    if background_tasks:
        background_tasks.add_task(
            email_service.send_email,
            inv.email,
            "Invitation to join",
            body,
        )
    else:
        await email_service.send_email(
            inv.email,
            "Invitation to join",
            body,
        )
    # Return invite summary (email, role, expires_at) so caller can show confirmation.
    return success_response(
        {
            "email": inv.email,
            "role": inv.role.value,
            "expires_at": inv.expires_at.isoformat(),
        },
        "Invitation sent",
    )


async def get_invitation_by_token(db: AsyncSession, token: str):
    """Get invitation by token. Raises 404 if not found; crud may filter expired (expires_at)."""
    inv = await invitation_crud.get_invitation_by_token(db, token)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or expired",
        )
    return inv


async def accept_invitation(
    db: AsyncSession,
    token: str,
    username: str,
    first_name: str,
    last_name: str,
    password: str,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """Complete registration: validate token, reject if already accepted or email/username taken, create user, mark accepted, send verify OTP. Email comes from invite."""
    inv = await get_invitation_by_token(db, token)
    if inv.accepted_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation already used",
        )
    existing = await user_crud.get_user_by_email_ci(db, inv.email, inv.tenant_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )
    existing_username = await user_crud.get_user_by_username_ci(
        db, username.strip(), inv.tenant_id
    )
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken in this organization",
        )
    user = await user_crud.create_user(
        db,
        tenant_id=inv.tenant_id,
        username=username.strip(),
        email=inv.email.lower().strip(),  # Email from invite, not request body.
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        hashed_password=hash_password(password),
        role=UserRole(inv.role.value),
        is_verified=False,
        is_active=False,
    )
    await invitation_crud.mark_accepted(db, inv.id)
    await db.flush()

    async def _send(email: str, subj: str, body: str) -> None:
        await email_service.send_email(email, subj, body)

    await db.commit()
    # Send verify_email OTP after commit so user exists when they hit verify-email endpoint.
    await send_otp(
        inv.email,
        "verify_email",
        inv.tenant_id,
        _send,
        subject="Verify your email",
        body_template="Your verification OTP is: {otp}. It expires in {minutes} minutes.",
        background_tasks=background_tasks,
    )
    return {
        "success": True,
        "message": "Registration successful. Please verify your email.",
    }
