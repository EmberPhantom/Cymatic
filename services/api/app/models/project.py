"""Project model"""

import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from cymatic_shared.db import Base


class ProjectStatus(str, enum.Enum):
    DRAFT = "draft"
    SPEC_GENERATING = "spec_generating"
    SPEC_READY = "spec_ready"
    SCENE_GENERATING = "scene_generating"
    SCENE_READY = "scene_ready"
    PUBLISHED = "published"
    FAILED = "failed"


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    domain = Column(String(50), nullable=False)
    category = Column(String(50), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, values_callable=lambda x: [e.value for e in x]),
        default=ProjectStatus.DRAFT,
        nullable=False,
    )
    description = Column(Text, nullable=True)
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

    organization = relationship("Organization", back_populates="projects")
    owner = relationship("User", back_populates="projects")
    specs = relationship("SimulationSpec", back_populates="project")
    assets = relationship("Asset", back_populates="project")
    scene_packages = relationship("ScenePackage", back_populates="project")
    stream_sessions = relationship("StreamSession", back_populates="project")
