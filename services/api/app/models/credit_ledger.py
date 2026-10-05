"""CreditLedger model"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, Index
from cymatic_shared.db import Base


class CreditLedger(Base):
    __tablename__ = "credit_ledger"
    __table_args__ = (
        # Balance SUM (organization_id prefix) + usage filter/order
        # (organization_id, event_type, created_at).
        Index(
            "ix_credit_ledger_org_event_created",
            "organization_id",
            "event_type",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    event_type = Column(String(100), nullable=False, default="manual_adjustment")
    amount = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    description = Column(String(255), nullable=True)
    reference_id = Column(Integer, nullable=True)
    reference_type = Column(String(50), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
