"""Fix audit_log drift - actor_id/metadata_json.

Revision ID: 005
Revises: 004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add actor_id if missing (legacy user_id)
    try:
        op.add_column("audit_logs", sa.Column("actor_id", sa.Integer(), nullable=True))
        op.create_foreign_key("fk_audit_logs_actor_id", "audit_logs", "users", ["actor_id"], ["id"], ondelete="SET NULL")
        op.execute("UPDATE audit_logs SET actor_id = user_id WHERE actor_id IS NULL AND user_id IS NOT NULL")
    except Exception:
        pass
    try:
        op.add_column("audit_logs", sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False))
        op.execute("UPDATE audit_logs SET metadata_json = COALESCE(details_json, '{}') WHERE metadata_json IS NULL")
    except Exception:
        pass
    # Ensure ip_address exists
    try:
        op.add_column("audit_logs", sa.Column("ip_address", sa.String(length=45), nullable=True))
    except Exception:
        pass
    # Make organization_id not nullable if was nullable
    try:
        op.execute("UPDATE audit_logs SET organization_id = 1 WHERE organization_id IS NULL")
        op.alter_column("audit_logs", "organization_id", nullable=False)
    except Exception:
        pass


def downgrade() -> None:
    pass
