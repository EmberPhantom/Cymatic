"""SimulationSpec model"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from cymatic_shared.db import Base


class SpecStatus(str, enum.Enum):
    DRAFT = "draft"
    VALIDATING = "validating"
    VALID = "valid"
    INVALID = "invalid"
    SUPERSEDED = "superseded"


class SimulationSpec(Base):
    __tablename__ = "simulation_specs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    payload_json = Column(JSON, nullable=False)
    status = Column(Enum(SpecStatus), default=SpecStatus.DRAFT, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="specs")
