"""Asset model"""
import enum
from datetime import datetime
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="assets")
