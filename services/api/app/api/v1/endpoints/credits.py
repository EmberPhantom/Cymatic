from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.dependencies import get_current_user, require_admin, require_owner, require_viewer
from app.db.session import get_db
from app.models.credit_ledger import CreditLedger
from app.models.organization import Organization
from app.models.user import User, UserRole

router = APIRouter()


class CreditBalance(BaseModel):
    balance: int
    currency: str = "credits"


class CreditLedgerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    event_type: str
    amount: int
    reference_id: Optional[int]
    reference_type: Optional[str]
    created_at: str


class CreditAdjustment(BaseModel):
    amount: int
    reason: str
    reference_id: Optional[int] = None
    reference_type: Optional[str] = None


# Credit costs for different operations
CREDIT_COSTS = {
    "spec_generation": 10,
    "scene_generation": 50,
    "scene_publish": 5,
    "stream_session_minute": 1,
    "voice_minute": 2,
    "asset_upload": 1,
    "asset_processing": 2,
}


@router.get("/balance", response_model=CreditBalance)
async def get_credit_balance(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(func.sum(CreditLedger.amount))
        .where(CreditLedger.organization_id == current_user.organization_id)
    )
    balance = result.scalar() or 0
    return CreditBalance(balance=balance)


@router.get("/usage", response_model=List[CreditLedgerResponse])
async def get_credit_usage(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    event_type: Optional[str] = None,
):
    query = select(CreditLedger).where(
        CreditLedger.organization_id == current_user.organization_id
    )
    
    if event_type:
        query = query.where(CreditLedger.event_type == event_type)
    
    query = query.order_by(CreditLedger.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/adjust", response_model=CreditBalance, status_code=status.HTTP_201_CREATED)
async def adjust_credits(
    adjustment: CreditAdjustment,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Adjust credit balance (admin/owner only) - positive for adding, negative for deducting"""
    ledger = CreditLedger(
        organization_id=current_user.organization_id,
        event_type="manual_adjustment",
        amount=adjustment.amount,
        reference_id=adjustment.reference_id,
        reference_type=adjustment.reference_type,
    )
    ledger.metadata_json = {"reason": adjustment.reason, "adjusted_by": current_user.id}
    db.add(ledger)
    await db.commit()
    
    # Return new balance
    result = await db.execute(
        select(func.sum(CreditLedger.amount))
        .where(CreditLedger.organization_id == current_user.organization_id)
    )
    balance = result.scalar() or 0
    return CreditBalance(balance=balance)


@router.get("/costs")
async def get_credit_costs(
    current_user: User = Depends(require_viewer),
):
    """Get credit costs for operations"""
    return CREDIT_COSTS


async def deduct_credits(
    db: AsyncSession,
    organization_id: int,
    event_type: str,
    amount: int,
    reference_id: Optional[int] = None,
    reference_type: Optional[str] = None,
) -> bool:
    """Deduct credits from organization balance. Returns True if successful."""
    # Check current balance
    result = await db.execute(
        select(func.sum(CreditLedger.amount))
        .where(CreditLedger.organization_id == organization_id)
    )
    balance = result.scalar() or 0
    
    if balance < amount:
        return False
    
    ledger = CreditLedger(
        organization_id=organization_id,
        event_type=event_type,
        amount=-amount,  # Negative for consumption
        reference_id=reference_id,
        reference_type=reference_type,
    )
    db.add(ledger)
    await db.commit()
    return True