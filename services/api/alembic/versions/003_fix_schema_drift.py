"""Fix schema drift - assets org, enums, agent actions, voice.

Revision ID: 003
Revises: 002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fix assetstatus enum - add 'uploading' if not exists (must be outside transaction)
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE assetstatus ADD VALUE IF NOT EXISTS 'uploading'")

    # Add organization_id to assets (tenant isolation)
    op.add_column("assets", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.create_index("ix_assets_organization_id", "assets", ["organization_id"])
    op.create_foreign_key("fk_assets_organization_id", "assets", "organizations", ["organization_id"], ["id"], ondelete="CASCADE")
    # Backfill from project.organization_id then set not nullable
    op.execute("UPDATE assets SET organization_id = (SELECT organization_id FROM projects WHERE projects.id = assets.project_id) WHERE organization_id IS NULL")
    op.alter_column("assets", "organization_id", nullable=False)

    # Fix agent_actions missing columns
    op.add_column("agent_actions", sa.Column("status", sa.String(length=50), server_default="pending", nullable=False))
    op.add_column("agent_actions", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

    # Fix voice_sessions missing columns
    op.add_column("voice_sessions", sa.Column("tts_audio_url", sa.String(length=512), nullable=True))
    op.add_column("voice_sessions", sa.Column("latency_ms", sa.Integer(), nullable=True))

    # Add unique constraint for spec version per project
    op.create_unique_constraint("uq_simulation_specs_project_version", "simulation_specs", ["project_id", "version"])

    # Add unique index for generation_runs input_hash where not failed
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_generation_runs_project_hash_active ON generation_runs (project_id, input_hash) WHERE status != 'failed'")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_generation_runs_project_hash_active")
    op.drop_constraint("uq_simulation_specs_project_version", "simulation_specs", type_="unique")
    op.drop_column("voice_sessions", "latency_ms")
    op.drop_column("voice_sessions", "tts_audio_url")
    op.drop_column("agent_actions", "completed_at")
    op.drop_column("agent_actions", "status")
    op.drop_constraint("fk_assets_organization_id", "assets", type_="foreignkey")
    op.drop_index("ix_assets_organization_id", table_name="assets")
    op.drop_column("assets", "organization_id")
    # Enum value removal requires recreation - skip
