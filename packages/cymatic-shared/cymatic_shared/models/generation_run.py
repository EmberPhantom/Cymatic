"""Durable state for a simulation generation workflow."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, Text, Index
from sqlalchemy.orm import relationship
from cymatic_shared.db import Base


class GenerationRun(Base):
    __tablename__ = "generation_runs"

    id = Column(String(64), primary_key=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    prompt = Column(Text, nullable=False)
    context_json = Column(JSON, nullable=False, default=dict)
    intake_json = Column(JSON, nullable=True)
    clarification_json = Column(JSON, nullable=False, default=dict)
    stage = Column(String(50), nullable=False, default="intake")
    status = Column(String(50), nullable=False, default="draft")
    progress = Column(Integer, nullable=False, default=0)
    error_json = Column(JSON, nullable=True)
    result_json = Column(JSON, nullable=True)
    input_hash = Column(String(64), nullable=False)
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

    project = relationship("Project")

    __table_args__ = (
        Index("ix_generation_runs_project_status", "project_id", "status"),
        Index("ix_generation_runs_project_input_hash", "project_id", "input_hash"),
    )


# Re-exported from model_enums (ORM-free home, safe for api's duplicate models).
from cymatic_shared.model_enums import RunStatus, RunStage  # noqa: F401,E402
