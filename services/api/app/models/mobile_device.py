"""MobileDevice model — device registry for the native render endpoint."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from cymatic_shared.db import Base


class MobileDevice(Base):
    """One row per (user, client-generated device_id).

    Devices auto-register on first render-session create. A revoked device
    (logout-all / lost phone) is rejected with 403 on session create.
    """

    __tablename__ = "mobile_devices"
    __table_args__ = (
        UniqueConstraint("user_id", "device_id", name="uq_mobile_devices_user_device"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    app_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="0.1.0"
    )
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
