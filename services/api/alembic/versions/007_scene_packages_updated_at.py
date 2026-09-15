"""Add missing updated_at to scene_packages (model requires it, 001 omitted it).

Revision ID: 007
Revises: 006
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scene_packages",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill from created_at, then enforce NOT NULL to match the ORM model.
    op.execute("UPDATE scene_packages SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column("scene_packages", "updated_at", nullable=False)


def downgrade() -> None:
    op.drop_column("scene_packages", "updated_at")
