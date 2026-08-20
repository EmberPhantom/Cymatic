"""CreditLedger model"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON
from cymatic_shared.db import Base


class CreditLedger(Base):
    __tablename__ = "credit_ledger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    description = Column(String(255), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
