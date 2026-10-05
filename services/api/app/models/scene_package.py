"""ScenePackage model"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, Index
from sqlalchemy.orm import relationship
from cymatic_shared.db import Base


class ScenePackage(Base):
    __tablename__ = "scene_packages"
    __table_args__ = (
        # get_latest_ready_scene_package() filters on (project_id, status).
        Index("ix_scene_packages_project_status", "project_id", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    spec_id = Column(Integer, ForeignKey("simulation_specs.id"), nullable=False)
    storage_key = Column(String(512), nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    metadata_json = Column(JSON, nullable=True)
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

    project = relationship("Project", back_populates="scene_packages")
    spec = relationship("SimulationSpec")
