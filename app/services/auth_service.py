"""Auth service: register (self + invite), verify email, login, OTP login, forgot password, refresh, logout. Uses JWT, OTP (Redis), and token blacklist."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants.auth_ttl import OTP_COOLDOWN, RESEND_WAIT_SECONDS
from app.constants.messages import (
    AUTH_INACTIVE,
    AUTH_INVALID_CREDENTIALS,
    AUTH_UNVERIFIED,
    LOGIN_OTP_SENT,
)
from app.crud import blacklist_crud, user_crud
from app.enums import UserRole
from app.models import User
from app.schemas.auth import (
    ForgotPasswordConfirmSchema,
    ForgotPasswordSchema,
    LoginSchema,
    RegisterSchema,
    ResendVerificationSchema,
    VerifyEmailSchema,
    VerifyLoginOTPSchema,
)
from app.services.email_service import email_service
from app.utils.jwt_handler import create_access_token, create_refresh_token
from app.utils.otp_handler import (
    _cooldown_key,
    otp_cooldown_message,
    send_otp,
    verify_otp,
)
from app.utils.password import hash_password, verify_password
from app.utils.redis_client import redis_client
from app.utils.response_helpers import success_response


def _is_self_deleted(user: User) -> bool:
    """True if user is soft-deleted by themselves (deleted_by == user.id). Only these users can re-register with same email."""
    return (
        user.deleted_at is not None
        and user.deleted_by is not None
        and user.deleted_by == user.id
    )


async def register_user(
    db: AsyncSession,
    data: RegisterSchema,
    tenant_id: UUID | None = None,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """Create INTERN user, send verification OTP. Allow re-registration only if self-deleted; admin-deleted returns 400."""
    # Check email/username across tenants and include soft-deleted to decide restore vs create vs conflict.
    existing_email = await user_crud.get_user_by_email_any_tenant_include_deleted(
        db, data.email
    )
    existing_username = await user_crud.get_user_by_username_ci_include_deleted(
        db, data.username, tenant_id
    )
    admin_deactivated_msg = (
        "This account was deleted by an admin. Please contact your admin."
    )

    if existing_email and existing_email.deleted_at is None:
        if existing_username and existing_username.deleted_at is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email and username already exist",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    if existing_email and existing_email.deleted_at is not None:
        if not _is_self_deleted(existing_email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=admin_deactivated_msg,
            )
        if existing_username and existing_username.id != existing_email.id:
            if existing_username.deleted_at is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already taken",
                )
            if not _is_self_deleted(existing_username):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=admin_deactivated_msg,
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken",
            )
    if existing_username and existing_username.deleted_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )
    if existing_username and existing_username.deleted_at is not None:
        if not _is_self_deleted(existing_username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=admin_deactivated_msg,
            )
        if existing_email is None or existing_email.id != existing_username.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken",
            )

    async def _send(email: str, subj: str, body: str) -> None:
        await email_service.send_email(email, subj, body)

    # Re-use same record: restore soft-deleted user and update fields; otherwise create new user.
    if existing_email and _is_self_deleted(existing_email):
        existing_email.restore()
        user = await user_crud.update_user(
            db,
            existing_email.id,
            include_deleted=True,
            username=data.username.strip(),
            email=data.email.lower().strip(),
            first_name=data.first_name.strip(),
            last_name=data.last_name.strip(),
            hashed_password=hash_password(data.password),
            role=UserRole.INTERN,
            tenant_id=tenant_id,
            is_verified=False,
            is_active=False,
            deleted_at=None,
            deleted_by=None,
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to restore user",
            )
        await db.commit()
        await db.refresh(user)
    else:
        user = await user_crud.create_user(
            db,
            username=data.username.strip(),
            email=data.email.lower().strip(),
            first_name=data.first_name.strip(),
            last_name=data.last_name.strip(),
            hashed_password=hash_password(data.password),
            role=UserRole.INTERN,
            tenant_id=tenant_id,
            is_verified=False,
            is_active=False,
        )
        await db.flush()
        await db.commit()
        await db.refresh(user)

    # tenant_id scopes OTP key so same email in different tenants gets different OTPs.
    await send_otp(
        data.email,
        "verify_email",
        tenant_id,
        _send,
        subject="Verify your email",
        body_template="Your verification OTP is: {otp}. It expires in {minutes} minutes.",
        background_tasks=background_tasks,
    )
    return {
        "success": True,
        "message": "Registration successful. Please verify your email.",
    }


async def verify_email(db: AsyncSession, data: VerifyEmailSchema) -> dict:
    """Verify email OTP and mark user verified. OTP key uses user's tenant_id so we resolve tenant before verify."""
    user = await user_crud.get_user_by_email_any_tenant(db, data.email)
    tenant_id = user.tenant_id if user else None
    await verify_otp(data.email, data.otp, "verify_email", tenant_id)
    if not user:
        user = await user_crud.get_user_by_email_any_tenant(db, data.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    await user_crud.update_user(db, user.id, is_verified=True, is_active=True)
    await db.commit()
    return {"success": True, "message": "Email verified successfully"}


async def resend_verification(
    db: AsyncSession,
    data: ResendVerificationSchema,
    tenant_id: UUID | None = None,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """Resend verification OTP. Rate-limited by RESEND_WAIT_SECONDS. Does not leak whether email is registered."""
    user = await user_crud.get_user_by_email_any_tenant(db, data.email)
    otp_tenant_id = user.tenant_id if user else tenant_id
    cooldown_key = _cooldown_key(data.email, "verify_email", otp_tenant_id)
    ttl = await redis_client.ttl(cooldown_key)
    if ttl > 0:
        elapsed = OTP_COOLDOWN - ttl
        if elapsed < RESEND_WAIT_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=otp_cooldown_message(ttl),
            )
    # Same message whether or not user exists (avoid email enumeration).
    if not user:
        return {
            "success": True,
            "message": "If this email is registered, a verification OTP has been sent.",
        }
    if user.is_verified:
        return {"success": True, "message": "Email already verified."}

    async def _send(email: str, subj: str, body: str) -> None:
        await email_service.send_email(email, subj, body)

    await send_otp(
        data.email,
        "verify_email",
        otp_tenant_id,
        _send,
        subject="Verify your email",
        body_template="Your verification OTP is: {otp}. It expires in {minutes} minutes.",
        background_tasks=background_tasks,
    )
    return {
        "success": True,
        "message": "Verification OTP sent. Please check your email.",
    }


async def login_with_password(db: AsyncSession, data: LoginSchema) -> dict:
    """Validate email+password and return access + refresh tokens. Reject deleted/unverified/inactive; self-deleted gets clear message."""
    user = await user_crud.get_user_by_email_any_tenant_include_deleted(db, data.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_INVALID_CREDENTIALS,
        )
    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_INVALID_CREDENTIALS,
        )
    # Order: credentials -> deleted (self vs admin) -> active -> verified, then issue tokens.
    if user.deleted_at is not None:
        if _is_self_deleted(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account was deleted. You can register again with the same email.",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deleted, please contact admin.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=AUTH_INACTIVE,
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=AUTH_UNVERIFIED,
        )
    access = create_access_token(user)
    refresh = create_refresh_token(user)
    return success_response({"access": access, "refresh": refresh})


async def login_otp_init(
    db: AsyncSession,
    data: LoginSchema,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """Step 1 of login-OTP: validate email+password, send login OTP. Same deleted/active/verified checks as password login."""
    user = await user_crud.get_user_by_email_any_tenant_include_deleted(db, data.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_INVALID_CREDENTIALS,
        )
    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_INVALID_CREDENTIALS,
        )
    if user.deleted_at is not None:
        if _is_self_deleted(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account was deleted. You can register again with the same email.",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deleted, please contact admin.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=AUTH_INACTIVE,
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=AUTH_UNVERIFIED,
        )

    async def _send(email: str, subj: str, body: str) -> None:
        await email_service.send_email(email, subj, body)

    await send_otp(
        data.email,
        "login",
        user.tenant_id,
        _send,
        subject="Your login OTP",
        body_template="Your login OTP is: {otp}. It expires in {minutes} minutes.",
        background_tasks=background_tasks,
    )
    return {"success": True, "message": LOGIN_OTP_SENT}


async def login_otp_verify(db: AsyncSession, data: VerifyLoginOTPSchema) -> dict:
    """Step 2 of login-OTP: verify OTP (key uses user.tenant_id), then return access + refresh tokens."""
    user = await user_crud.get_user_by_email_any_tenant(db, data.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    await verify_otp(data.email, data.otp, "login", user.tenant_id)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=AUTH_INACTIVE,
        )
    access = create_access_token(user)
    refresh = create_refresh_token(user)
    return success_response({"access": access, "refresh": refresh})


async def forgot_password(
    db: AsyncSession,
    data: ForgotPasswordSchema,
    tenant_id: UUID | None = None,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """Send reset-password OTP to email. Same success message whether user exists (avoid email enumeration)."""
    user = await user_crud.get_user_by_email_any_tenant(db, data.email)
    if not user:
        return {
            "success": True,
            "message": "If this email is registered, a reset OTP has been sent.",
        }

    async def _send(email: str, subj: str, body: str) -> None:
        await email_service.send_email(email, subj, body)

    # Use tenant_id from request or user so OTP key matches what we use in forgot_password_confirm.
    await send_otp(
        data.email,
        "reset_password",
        tenant_id or user.tenant_id,
        _send,
        subject="Reset your password",
        body_template="Your password reset OTP is: {otp}. It expires in {minutes} minutes.",
        background_tasks=background_tasks,
    )
    return {
        "success": True,
        "message": "If this email is registered, a reset OTP has been sent.",
    }


async def forgot_password_confirm(
    db: AsyncSession,
    data: ForgotPasswordConfirmSchema,
) -> dict:
    """Verify reset OTP and set new password. OTP key uses user.tenant_id (must match forgot_password)."""
    user = await user_crud.get_user_by_email_any_tenant(db, data.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    await verify_otp(
        data.email,
        data.otp,
        "reset_password",
        user.tenant_id,
    )
    await user_crud.update_user(
        db,
        user.id,
        hashed_password=hash_password(data.new_password),
    )
    await db.commit()
    return {"success": True, "message": "Password reset successfully."}


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> dict:
    """Validate refresh token, blacklist old one, return new access + refresh. Reject if already blacklisted or user gone."""
    try:
        payload = jwt.decode(
            refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )
    jti = payload.get("jti")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    if await blacklist_crud.is_token_blacklisted(db, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )
    user = await user_crud.get_user(db, UUID(sub))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    exp = payload.get("exp")
    if exp:
        expires_at = datetime.fromtimestamp(exp, tz=UTC)
    else:
        expires_at = datetime.now(UTC) + timedelta(days=7)
    # Blacklist old refresh so it cannot be reused (refresh rotation).
    await blacklist_crud.blacklist_token(db, user.id, jti, expires_at)
    await db.commit()

    access = create_access_token(user)
    new_refresh = create_refresh_token(user)
    return success_response({"access": access, "refresh": new_refresh})


async def logout(db: AsyncSession, user: User, refresh_token: str) -> dict:
    """Blacklist the refresh token JTI. verify_exp=False so we can blacklist even expired tokens."""
    try:
        payload = jwt.decode(
            refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid refresh token",
        )
    jti = payload.get("jti")
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid refresh token",
        )
    if await blacklist_crud.is_token_blacklisted(db, jti):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user already logged out",
        )
    # Store expires_at for blacklist entry so we can prune expired rows later.
    exp = payload.get("exp")
    if exp:
        expires_at = datetime.fromtimestamp(exp, tz=UTC)
    else:
        expires_at = datetime.now(UTC) + timedelta(days=30)
    await blacklist_crud.blacklist_token(db, user.id, jti, expires_at)
    await db.commit()
    return {"success": True, "message": "Logged out successfully"}
