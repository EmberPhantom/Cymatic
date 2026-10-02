"""Add missing updated_at to scene_packages (parity with API chain rev 007).

Revision ID: 006
Revises: 005
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scene_packages",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE scene_packages SET updated_at = created_at WHERE updated_at IS NULL"
    )
    op.alter_column("scene_packages", "updated_at", nullable=False)


def downgrade() -> None:
    op.drop_column("scene_packages", "updated_at")
