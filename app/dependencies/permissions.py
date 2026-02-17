"""Role-based dependencies: require one of the given roles or tenant/super-admin for tenant APIs."""

from fastapi import Depends, HTTPException, status

from app.constants.messages import MENTOR_TENANT_API_MESSAGE
from app.dependencies.user import get_current_user
from app.enums import UserRole
from app.models import User


def require_roles(*allowed_roles: UserRole):
    """Returns a dependency that requires current user's role to be one of allowed_roles. Use e.g. Depends(require_roles(UserRole.TENANT_ADMIN))."""

    async def _require(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _require


async def require_super_admin_for_tenant_apis(
    current_user: User = Depends(get_current_user),
) -> User:
    """For tenant router: block MENTOR explicitly, then require SUPER_ADMIN (e.g. list tenants, create tenant)."""
    # MENTOR is explicitly blocked from all tenant management; use a clear message.
    if current_user.role == UserRole.MENTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=MENTOR_TENANT_API_MESSAGE,
        )
    # Only SUPER_ADMIN can list/create tenants; TENANT_ADMIN and INTERN get generic 403.
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only super admin can access this resource.",
        )
    return current_user


async def require_tenant_admin_or_super_for_tenant_apis(
    current_user: User = Depends(get_current_user),
) -> User:
    """For tenant router: block MENTOR, then require TENANT_ADMIN or SUPER_ADMIN (e.g. get/update/delete tenant)."""
    # Same as above: MENTOR cannot access tenant APIs at all.
    if current_user.role == UserRole.MENTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=MENTOR_TENANT_API_MESSAGE,
        )
    # TENANT_ADMIN can manage own tenant; SUPER_ADMIN can manage any. INTERN gets 403.
    if current_user.role not in (UserRole.TENANT_ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only tenant admin or super admin can view or manage this resource.",
        )
    return current_user
