"""Fix credit_ledger drift - add balance_after/description/metadata_json.

Revision ID: 004
Revises: 003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add missing columns from shared model
    op.add_column("credit_ledger", sa.Column("balance_after", sa.Integer(), nullable=True))
    op.add_column("credit_ledger", sa.Column("description", sa.String(length=255), nullable=True))
    op.add_column("credit_ledger", sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    # Backfill balance_after from amount where possible (initial 0)
    op.execute("UPDATE credit_ledger SET balance_after = amount WHERE balance_after IS NULL")
    op.alter_column("credit_ledger", "balance_after", nullable=False)
    # Keep event_type/reference columns for backward compat, ensure they exist
    # If migration 001 lacked balance_after, this completes schema


def downgrade() -> None:
    op.drop_column("credit_ledger", "metadata_json")
    op.drop_column("credit_ledger", "description")
    op.drop_column("credit_ledger", "balance_after")
