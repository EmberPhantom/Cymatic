"""Mobile render sessions: device registry + heartbeat columns.

Revision ID: 008
Revises: 007
"""

from alembic import op
import sqlalchemy as sa


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mobile_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column(
            "app_version", sa.String(length=32), nullable=False, server_default="0.1.0"
        ),
        sa.Column(
            "revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "device_id", name="uq_mobile_devices_user_device"
        ),
    )
    op.create_index("ix_mobile_devices_user", "mobile_devices", ["user_id"])
    op.add_column(
        "stream_sessions", sa.Column("device_id", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "stream_sessions",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stream_sessions", "last_heartbeat_at")
    op.drop_column("stream_sessions", "device_id")
    op.drop_index("ix_mobile_devices_user", table_name="mobile_devices")
    op.drop_table("mobile_devices")
