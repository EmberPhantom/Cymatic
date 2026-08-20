"""Initial migration

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types
    user_role = sa.Enum('owner', 'admin', 'creator', 'viewer', 'auditor', name='userrole')
    user_role.create(op.get_bind())

    project_status = sa.Enum('draft', 'spec_generating', 'spec_ready', 'scene_generating', 'scene_ready', 'published', 'failed', name='projectstatus')
    project_status.create(op.get_bind())

    spec_status = sa.Enum('draft', 'validating', 'valid', 'invalid', 'superseded', name='specstatus')
    spec_status.create(op.get_bind())

    asset_type = sa.Enum('model_3d', 'texture', 'audio', 'material', 'image', 'other', name='assettype')
    asset_type.create(op.get_bind())

    asset_status = sa.Enum('uploaded', 'processing', 'ready', 'failed', name='assetstatus')
    asset_status.create(op.get_bind())

    stream_session_status = sa.Enum('pending', 'connecting', 'active', 'disconnected', 'failed', name='streamsessionstatus')
    stream_session_status.create(op.get_bind())

    # organizations table
    op.create_table(
        'organizations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('plan', sa.String(length=50), nullable=False, server_default='free'),
        sa.Column('settings_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_organizations_id', 'organizations', ['id'], unique=False)

    # users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', user_role, nullable=False, server_default='creator'),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_users_id', 'users', ['id'], unique=False)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_organization_id', 'users', ['organization_id'], unique=False)

    # projects table
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('domain', sa.String(length=50), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('status', project_status, nullable=False, server_default='draft'),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_projects_id', 'projects', ['id'], unique=False)
    op.create_index('ix_projects_organization_id', 'projects', ['organization_id'], unique=False)

    # simulation_specs table
    op.create_table(
        'simulation_specs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', spec_status, nullable=False, server_default='draft'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_simulation_specs_id', 'simulation_specs', ['id'], unique=False)
    op.create_index('ix_simulation_specs_project_id', 'simulation_specs', ['project_id'], unique=False)

    # assets table
    op.create_table(
        'assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('storage_key', sa.String(length=512), nullable=False),
        sa.Column('type', asset_type, nullable=False),
        sa.Column('status', asset_status, nullable=False, server_default='uploaded'),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_assets_id', 'assets', ['id'], unique=False)
    op.create_index('ix_assets_project_id', 'assets', ['project_id'], unique=False)

    # scene_packages table
    op.create_table(
        'scene_packages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('spec_id', sa.Integer(), nullable=False),
        sa.Column('storage_key', sa.String(length=512), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='generating'),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['spec_id'], ['simulation_specs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_scene_packages_id', 'scene_packages', ['id'], unique=False)
    op.create_index('ix_scene_packages_project_id', 'scene_packages', ['project_id'], unique=False)

    # stream_sessions table
    op.create_table(
        'stream_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', stream_session_status, nullable=False, server_default='pending'),
        sa.Column('signaling_session_id', sa.String(length=255), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_stream_sessions_id', 'stream_sessions', ['id'], unique=False)
    op.create_index('ix_stream_sessions_project_id', 'stream_sessions', ['project_id'], unique=False)
    op.create_index('ix_stream_sessions_user_id', 'stream_sessions', ['user_id'], unique=False)

    # runtime_events table
    op.create_table(
        'runtime_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['stream_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_runtime_events_id', 'runtime_events', ['id'], unique=False)
    op.create_index('ix_runtime_events_session_id', 'runtime_events', ['session_id'], unique=False)
    op.create_index('ix_runtime_events_event_type', 'runtime_events', ['event_type'], unique=False)

    # agent_actions table
    op.create_table(
        'agent_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.String(length=100), nullable=False),
        sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['stream_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_agent_actions_id', 'agent_actions', ['id'], unique=False)
    op.create_index('ix_agent_actions_session_id', 'agent_actions', ['session_id'], unique=False)

    # voice_sessions table
    op.create_table(
        'voice_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('response_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['stream_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_voice_sessions_id', 'voice_sessions', ['id'], unique=False)
    op.create_index('ix_voice_sessions_session_id', 'voice_sessions', ['session_id'], unique=False)

    # credit_ledger table
    op.create_table(
        'credit_ledger',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('reference_id', sa.Integer(), nullable=True),
        sa.Column('reference_type', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_credit_ledger_id', 'credit_ledger', ['id'], unique=False)
    op.create_index('ix_credit_ledger_organization_id', 'credit_ledger', ['organization_id'], unique=False)

    # audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=False),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_logs_id', 'audit_logs', ['id'], unique=False)
    op.create_index('ix_audit_logs_organization_id', 'audit_logs', ['organization_id'], unique=False)
    op.create_index('ix_audit_logs_actor_id', 'audit_logs', ['actor_id'], unique=False)
    op.create_index('ix_audit_logs_resource_type', 'audit_logs', ['resource_type'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('audit_logs')
    op.drop_table('credit_ledger')
    op.drop_table('voice_sessions')
    op.drop_table('agent_actions')
    op.drop_table('runtime_events')
    op.drop_table('stream_sessions')
    op.drop_table('scene_packages')
    op.drop_table('assets')
    op.drop_table('simulation_specs')
    op.drop_table('projects')
    op.drop_table('users')
    op.drop_table('organizations')

    # Drop enum types
    sa.Enum(name='streamsessionstatus').drop(op.get_bind())
    sa.Enum(name='assetstatus').drop(op.get_bind())
    sa.Enum(name='assettype').drop(op.get_bind())
    sa.Enum(name='specstatus').drop(op.get_bind())
    sa.Enum(name='projectstatus').drop(op.get_bind())
    sa.Enum(name='userrole').drop(op.get_bind())
