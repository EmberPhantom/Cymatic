"""Fix asset model/migration drift + hot-path indexes.

Revision ID: 009
Revises: 008

Asset drift vs 001_initial.py:
- assets.project_id was created NOT NULL, but the ORM model and the
  upload-init endpoint allow org-level (project-less) assets
  (nullable=True) -> relax to NULL.
- assets.updated_at was created nullable, but the ORM model (like every
  sibling model) requires NOT NULL -> backfill from created_at, then
  enforce NOT NULL (same pattern as 007 for scene_packages).
- assets.status server_default parity is model-side only
  (server_default="uploaded" on the ORM column; the DB default from 001
  already matches), so no DDL is needed for it.

Indexes (models carry the same Index() in __table_args__):
- ix_stream_sessions_user_status_heartbeat: heartbeat sweep in render.py
  filters (user_id, status, last_heartbeat_at).
- ix_scene_packages_project_status: get_latest_ready_scene_package()
  filters (project_id, status).
- ix_credit_ledger_org_event_created: balance SUM (organization_id
  prefix) + usage filter/order (organization_id, event_type, created_at).
"""

from alembic import op
import sqlalchemy as sa


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # assets.project_id: NOT NULL -> NULL (org-level assets).
    op.alter_column("assets", "project_id", nullable=True)

    # assets.updated_at: backfill NULLs, then enforce NOT NULL.
    op.execute(
        "UPDATE assets SET updated_at = created_at "
        "WHERE updated_at IS NULL"
    )
    op.alter_column("assets", "updated_at", nullable=False)

    op.create_index(
        "ix_stream_sessions_user_status_heartbeat",
        "stream_sessions",
        ["user_id", "status", "last_heartbeat_at"],
    )
    op.create_index(
        "ix_scene_packages_project_status",
        "scene_packages",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_credit_ledger_org_event_created",
        "credit_ledger",
        ["organization_id", "event_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_credit_ledger_org_event_created", table_name="credit_ledger"
    )
    op.drop_index(
        "ix_scene_packages_project_status", table_name="scene_packages"
    )
    op.drop_index(
        "ix_stream_sessions_user_status_heartbeat",
        table_name="stream_sessions",
    )
    op.alter_column("assets", "updated_at", nullable=True)
    op.alter_column("assets", "project_id", nullable=False)
