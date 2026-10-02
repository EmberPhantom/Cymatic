"""PlanningSheet model — frozen, reviewable planning output."""

import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from cymatic_shared.db import Base


class SheetStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class PlanningSheet(Base):
    __tablename__ = "planning_sheets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    run_id = Column(
        String(64), ForeignKey("generation_runs.id", ondelete="SET NULL"), nullable=True
    )
    version = Column(Integer, nullable=False, default=1)
    payload_json = Column(JSON, nullable=False)
    status: Mapped[SheetStatus] = mapped_column(
        Enum(SheetStatus, values_callable=lambda x: [e.value for e in x]),
        default=SheetStatus.DRAFT,
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    project = relationship("Project", back_populates="planning_sheets")
