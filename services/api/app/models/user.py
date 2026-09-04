"""User model"""

import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, Enum, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from cymatic_shared.db import Base


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    CREATOR = "creator"
    VIEWER = "viewer"
    AUDITOR = "auditor"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(
        Enum(UserRole, values_callable=lambda x: [e.value for e in x]),
        default=UserRole.CREATOR,
        nullable=False,
    )
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
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

    organization = relationship("Organization", back_populates="users")
    projects = relationship("Project", back_populates="owner")
