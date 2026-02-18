"""Auth routes: register, login, OTP, verify email, forgot password, refresh, logout. Most endpoints do not require JWT."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import tenant_crud
from app.database.init_db import get_db
from app.dependencies.rate_limit import rate_limit_public
from app.dependencies.user import get_current_user
from app.models import User
from app.schemas.auth import (
    ForgotPasswordConfirmSchema,
    ForgotPasswordSchema,
    InviteRegisterSchema,
    LoginSchema,
    RefreshSchema,
    RegisterSchema,
    ResendVerificationSchema,
    VerifyEmailSchema,
    VerifyLoginOTPSchema,
)
from app.services import auth_service

# All routes under /auth; only logout (and optionally refresh) require a valid JWT.
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/tenants/{tenant_id}/register",
    status_code=status.HTTP_201_CREATED,
)
async def register(
    tenant_id: UUID,
    data: RegisterSchema,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_public),
):
    """Self signup (INTERN) for the given tenant. Tenant must exist and be active."""
    tenant = await tenant_crud.get_tenant(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    # Reject signup if tenant has disabled signups (is_active=False).
    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant is not accepting signups",
        )
    return await auth_service.register_user(
        db, data, tenant_id=tenant_id, background_tasks=background_tasks
    )


@router.post(
    "/invite/{invite_token}/register/",
    status_code=status.HTTP_201_CREATED,
)
async def register_with_invite(
    invite_token: str,
    data: InviteRegisterSchema,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_public),
):
    """Complete registration using invitation token (email from invite)."""
    from app.services import invitation_service  # Lazy import to avoid circular imports.

    return await invitation_service.accept_invitation(
        db,
        token=invite_token,
        username=data.username,
        first_name=data.first_name,
        last_name=data.last_name,
        password=data.password,
        background_tasks=background_tasks,
    )


@router.post(
    "/verify-email",
    status_code=status.HTTP_200_OK,
)
async def verify_email(
    data: VerifyEmailSchema,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_public),
):
    """Verify email with OTP."""
    return await auth_service.verify_email(db, data)


@router.post(
    "/resend-verification",
    status_code=status.HTTP_200_OK,
)
async def resend_verification(
    data: ResendVerificationSchema,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_public),
):
    """Resend verification OTP."""
    # tenant_id=None: email is globally unique; service resolves tenant from user if needed for OTP key.
    return await auth_service.resend_verification(
        db, data, tenant_id=None, background_tasks=background_tasks
    )


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
)
async def login_with_password(
    data: LoginSchema,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_public),
):
    """Login with email and password. Returns access and refresh tokens."""
    return await auth_service.login_with_password(db, data)


@router.post(
    "/login-otp",
    status_code=status.HTTP_200_OK,
)
async def login(
    data: LoginSchema,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_public),
):
    """Step 1: Validate email+password, send login OTP."""
    return await auth_service.login_otp_init(
        db, data, background_tasks=background_tasks
    )


@router.post(
    "/login/verify-otp",
    status_code=status.HTTP_200_OK,
)
async def login_verify_otp(
    data: VerifyLoginOTPSchema,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_public),
):
    """Step 2: Verify OTP and return access + refresh tokens."""
    return await auth_service.login_otp_verify(db, data)


@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
)
async def forgot_password(
    data: ForgotPasswordSchema,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_public),
):
    """Request password reset OTP."""
    # tenant_id=None: email is globally unique; service looks up user and may use tenant for OTP key.
    return await auth_service.forgot_password(
        db, data, tenant_id=None, background_tasks=background_tasks
    )


@router.post(
    "/forgot-password/confirm",
    status_code=status.HTTP_200_OK,
)
async def forgot_password_confirm(
    data: ForgotPasswordConfirmSchema,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_public),
):
    """Confirm reset with OTP and new password."""
    return await auth_service.forgot_password_confirm(db, data)


@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
)
async def refresh(
    data: RefreshSchema,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_public),
):
    """Refresh access token; old refresh token is blacklisted. No auth header required—only refresh token in body."""
    return await auth_service.refresh_tokens(db, data.refresh)


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
)
async def logout(
    data: RefreshSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Blacklist the refresh token. Requires JWT so we know which user is logging out and can validate the token."""
    return await auth_service.logout(db, current_user, data.refresh)
