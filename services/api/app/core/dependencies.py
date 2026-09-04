from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError
from app.core.config import get_settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User, UserRole

settings = get_settings()
security = HTTPBearer(auto_error=False)


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = status.HTTP_401_UNAUTHORIZED):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user from JWT token."""
    token = (
        credentials.credentials
        if credentials
        else request.cookies.get("cymatic_access_token")
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token)
        if payload.get("type") not in ("access", None):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise AuthError("Invalid token payload")
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check token revocation
    from app.core.security import is_token_revoked

    if await is_token_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    # Populate request state for audit middleware
    request.state.user_id = user.id
    request.state.organization_id = user.organization_id
    request.state.user_role = user.role

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user (alias for clarity)."""
    return current_user


def require_roles(*allowed_roles: UserRole):
    """Dependency factory for role-based access control."""

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {[r.value for r in allowed_roles]}",
            )
        return current_user

    return role_checker


# Common role dependencies
require_owner = require_roles(UserRole.OWNER)
require_admin = require_roles(UserRole.OWNER, UserRole.ADMIN)
require_creator = require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.CREATOR)
require_viewer = require_roles(
    UserRole.OWNER, UserRole.ADMIN, UserRole.CREATOR, UserRole.VIEWER, UserRole.AUDITOR
)


async def get_organization_id(
    current_user: User = Depends(get_current_user),
) -> int:
    """Get current user's organization ID."""
    return current_user.organization_id


class TenantContext:
    """Request-scoped tenant context."""

    def __init__(self, organization_id: int, user_id: int, user_role: UserRole):
        self.organization_id = organization_id
        self.user_id = user_id
        self.user_role = user_role


async def get_tenant_context(
    current_user: User = Depends(get_current_user),
) -> TenantContext:
    """Get tenant context for the current request."""
    return TenantContext(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )
