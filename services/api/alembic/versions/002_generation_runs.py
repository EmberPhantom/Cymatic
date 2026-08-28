"""Add durable generation workflow state.

Revision ID: 002
Revises: 001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("intake_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("clarification_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("stage", sa.String(length=50), nullable=False, server_default="intake"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generation_runs_project_status", "generation_runs", ["project_id", "status"])
    op.create_index("ix_generation_runs_project_input_hash", "generation_runs", ["project_id", "input_hash"])


def downgrade() -> None:
    op.drop_index("ix_generation_runs_project_input_hash", table_name="generation_runs")
    op.drop_index("ix_generation_runs_project_status", table_name="generation_runs")
    op.drop_table("generation_runs")
