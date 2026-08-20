"""StreamSession model"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from cymatic_shared.db import Base


class StreamSessionStatus(str, enum.Enum):
    PENDING = "pending"
    CONNECTING = "connecting"
    ACTIVE = "active"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


class StreamSession(Base):
    __tablename__ = "stream_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(StreamSessionStatus), default=StreamSessionStatus.PENDING, nullable=False)
    signaling_session_id = Column(String(255), nullable=True)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="stream_sessions")
