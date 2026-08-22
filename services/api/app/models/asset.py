"""Asset model"""
import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
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
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    storage_key = Column(String(512), nullable=False)
    type = Column(Enum(AssetType), nullable=False)
    status = Column(Enum(AssetStatus), default=AssetStatus.UPLOADED, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    project = relationship("Project", back_populates="assets")
