"""Asset model"""

import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from cymatic_shared.db import Base


class AssetType(str, enum.Enum):
    MODEL_3D = "model_3d"
    TEXTURE = "texture"
    AUDIO = "audio"
    MATERIAL = "material"
    IMAGE = "image"
    OTHER = "other"


class AssetStatus(str, enum.Enum):
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    storage_key = Column(String(512), nullable=False)
    type: Mapped[AssetType] = mapped_column(
        Enum(AssetType, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, values_callable=lambda x: [e.value for e in x]),
        default=AssetStatus.UPLOADED,
        nullable=False,
    )
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

    organization = relationship("Organization")
    project = relationship("Project", back_populates="assets")
