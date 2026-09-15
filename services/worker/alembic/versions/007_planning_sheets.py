"""Add planning_sheets table for the planning agent output (parity with API rev 006).

Revision ID: 007
Revises: 006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DO $$ BEGIN CREATE TYPE sheetstatus AS ENUM ('draft', 'approved', 'superseded'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    sheet_status = postgresql.ENUM("draft", "approved", "superseded", name="sheetstatus", create_type=False)
    op.create_table(
        "planning_sheets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sheet_status, nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["generation_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_planning_sheets_project_status", "planning_sheets", ["project_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_planning_sheets_project_status", table_name="planning_sheets")
    op.drop_table("planning_sheets")
    postgresql.ENUM(name="sheetstatus").drop(op.get_bind(), checkfirst=True)
