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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns("audit_logs")}

    # Add actor_id if missing (legacy user_id). Inspect before altering instead
    # of catching errors in a transaction that has already been aborted.
    if "actor_id" not in columns:
        op.add_column("audit_logs", sa.Column("actor_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_audit_logs_actor_id",
            "audit_logs",
            "users",
            ["actor_id"],
            ["id"],
            ondelete="SET NULL",
        )
        if "user_id" in columns:
            op.execute(
                "UPDATE audit_logs SET actor_id = user_id WHERE actor_id IS NULL AND user_id IS NOT NULL"
            )

    if "metadata_json" not in columns:
        op.add_column(
            "audit_logs",
            sa.Column(
                "metadata_json",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default="{}",
                nullable=False,
            ),
        )
        if "details_json" in columns:
            op.execute(
                "UPDATE audit_logs SET metadata_json = COALESCE(details_json, '{}') WHERE metadata_json IS NULL"
            )

    if "ip_address" not in columns:
        op.add_column(
            "audit_logs", sa.Column("ip_address", sa.String(length=45), nullable=True)
        )

    organization = columns.get("organization_id")
    if organization and organization.get("nullable"):
        op.execute(
            "UPDATE audit_logs SET organization_id = 1 WHERE organization_id IS NULL"
        )
        op.alter_column("audit_logs", "organization_id", nullable=False)


def downgrade() -> None:
    pass
