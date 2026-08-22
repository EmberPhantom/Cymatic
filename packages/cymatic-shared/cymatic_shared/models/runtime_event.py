"""RuntimeEvent model"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON
from cymatic_shared.db import Base


class RuntimeEvent(Base):
    __tablename__ = "runtime_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("stream_sessions.id"), nullable=False)
    event_type = Column(String(100), nullable=False)
    payload_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
