from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.dependencies import get_current_user, require_admin, require_owner
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.organization import Organization

router = APIRouter()


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: str
    organization_id: int
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "creator"


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("", response_model=List[UserResponse])
async def list_users(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    result = await db.execute(
        select(User).where(User.organization_id == current_user.organization_id)
        .offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.post("/invite", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def invite_user(
    user_data: UserCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Check if user exists
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Validate role
    try:
        role = UserRole(user_data.role)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    # Only owner can create owner/admin
    if role in [UserRole.OWNER, UserRole.ADMIN] and current_user.role != UserRole.OWNER:
        raise HTTPException(status_code=403, detail="Cannot assign this role")
    
    user = User(
        email=user_data.email,
        name=user_data.name,
        hashed_password=get_password_hash(user_data.password),
        role=role,
        organization_id=current_user.organization_id,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.id == user_id, User.organization_id == current_user.organization_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent self-demotion
    if user.id == current_user.id and user_update.role and user_update.role != current_user.role.value:
        raise HTTPException(status_code=400, detail="Cannot change own role")
    
    # Only owner can promote to owner/admin
    if user_update.role:
        try:
            new_role = UserRole(user_update.role)
            if new_role in [UserRole.OWNER, UserRole.ADMIN] and current_user.role != UserRole.OWNER:
                raise HTTPException(status_code=403, detail="Cannot assign this role")
            user.role = new_role
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid role")
    
    if user_update.name is not None:
        user.name = user_update.name
    if user_update.is_active is not None:
        user.is_active = user_update.is_active
    
    await db.commit()
    await db.refresh(user)
    return user