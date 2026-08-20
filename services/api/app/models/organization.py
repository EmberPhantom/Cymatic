"""Organization model"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from cymatic_shared.db import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    plan = Column(String(50), default="free", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    users = relationship("User", back_populates="organization")
    projects = relationship("Project", back_populates="organization")
