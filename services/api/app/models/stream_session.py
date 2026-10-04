"""StreamSession model"""

import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from cymatic_shared.db import Base


class StreamSessionStatus(str, enum.Enum):
    PENDING = "pending"
    CONNECTING = "connecting"
    ACTIVE = "active"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


class StreamSession(Base):
    __tablename__ = "stream_sessions"
    __table_args__ = (
        # Heartbeat sweep in render.py filters on (user_id, status,
        # last_heartbeat_at): composite index avoids a full-user scan.
        Index(
            "ix_stream_sessions_user_status_heartbeat",
            "user_id",
            "status",
            "last_heartbeat_at",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status: Mapped[StreamSessionStatus] = mapped_column(
        Enum(StreamSessionStatus, values_callable=lambda x: [e.value for e in x]),
        default=StreamSessionStatus.PENDING,
        nullable=False,
    )
    signaling_session_id = Column(String(255), nullable=True)
    # Native render sessions: which registered device is rendering.
    device_id = Column(String(128), nullable=True)
    # Last render heartbeat; sessions silent >10 min are swept to DISCONNECTED.
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    project = relationship("Project", back_populates="stream_sessions")
