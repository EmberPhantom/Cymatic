"""AgentAction model"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON
from cymatic_shared.db import Base


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("stream_sessions.id"), nullable=False)
    action_type = Column(String(100), nullable=False)
    payload_json = Column(JSON, nullable=True)
    status = Column(String(50), default="pending", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime, nullable=True)
