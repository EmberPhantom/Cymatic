from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional
from datetime import timedelta
from jose import JWTError
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
    get_password_hash,
    decode_token,
    revoke_token,
    is_token_revoked,
)
from app.core.dependencies import get_current_user, security
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.user import User, UserRole
from app.models.organization import Organization

router = APIRouter()
settings = get_settings()


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    email: Optional[str] = None


class RefreshRequest(BaseModel):
    token: Optional[str] = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=1, max_length=100)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: str
    organization_id: int
    is_active: bool


class OrganizationCreate(BaseModel):
    name: str


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    plan: str


@router.post(
    "/login",
    response_model=Token,
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_AUTH))],
)
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "org_id": user.organization_id},
        expires_delta=timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )

    _set_auth_cookies(response, access_token, refresh_token)
    return Token(access_token=access_token, refresh_token=refresh_token)


def _set_auth_cookies(
    response: Response, access_token: str, refresh_token: str
) -> None:
    secure = settings.ENVIRONMENT == "production"
    response.set_cookie(
        "cymatic_access_token",
        access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        "cymatic_refresh_token",
        refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/v1/auth",
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_AUTH))],
)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    org = Organization(name=f"{user_data.name}'s Organization", plan="free")
    db.add(org)
    await db.flush()

    hashed_password = get_password_hash(user_data.password)
    user = User(
        email=user_data.email,
        name=user_data.name,
        hashed_password=hashed_password,
        role=UserRole.CREATOR,
        organization_id=org.id,
        is_active=True,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent same-email register won the race after the
        # check-then-insert above: report conflict, not a 500.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    await db.refresh(user)

    return user


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.post(
    "/refresh",
    response_model=Token,
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_AUTH_REFRESH))],
)
async def refresh_token(
    response: Response,
    http_request: Request,
    refresh_request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    token = refresh_request.token or http_request.cookies.get("cymatic_refresh_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is required"
        )
    try:
        payload = decode_token(token)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if await is_token_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is not a refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_id_int))
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

    new_access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "org_id": user.organization_id},
        expires_delta=timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    new_refresh_token = create_refresh_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )

    await revoke_token(token)

    _set_auth_cookies(response, new_access_token, new_refresh_token)
    return Token(access_token=new_access_token, refresh_token=new_refresh_token)


@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Revoke the current access token."""
    from app.core.security import revoke_token

    token = (
        credentials.credentials
        if credentials
        else request.cookies.get("cymatic_access_token")
    )
    if token:
        await revoke_token(token)
    response.delete_cookie("cymatic_access_token", path="/")
    response.delete_cookie("cymatic_refresh_token", path="/v1/auth")
    return {"message": "Successfully logged out"}
