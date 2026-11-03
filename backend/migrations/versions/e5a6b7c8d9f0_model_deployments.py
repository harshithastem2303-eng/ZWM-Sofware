"""v1.1.0 Block A4: candidate approvals, controlled deployments and deployment audit log

Additive only: three new tables, no change to existing rows. model_deployments and
deployment_events store model ids without foreign keys so the history survives
later model/job cleanup.

Revision ID: e5a6b7c8d9f0
Revises: d4f5a6b7c8e9
Create Date: 2026-10-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5a6b7c8d9f0'
down_revision = 'd4f5a6b7c8e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'model_approvals',
        sa.Column('approval_id', sa.String(length=36), nullable=False),
        sa.Column('model_id', sa.String(length=36), nullable=False),
        sa.Column('model_version', sa.String(length=20), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=False),
        sa.Column('evaluation_id', sa.String(length=36), nullable=False),
        sa.Column('evaluation_config_hash', sa.String(length=64), nullable=False),
        sa.Column('evaluation_status', sa.String(length=20), nullable=False),
        sa.Column('gate_decision', sa.String(length=32), nullable=True),
        sa.Column('weights_sha256', sa.String(length=64), nullable=False),
        sa.Column('class_map_sha256', sa.String(length=64), nullable=False),
        sa.Column('manifest_sha256', sa.String(length=64), nullable=True),
        sa.Column('decision', sa.String(length=16), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('decided_by', sa.String(length=36), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['model_id'], ['model_versions.model_id']),
        sa.ForeignKeyConstraint(['job_id'], ['training_jobs.job_id']),
        sa.ForeignKeyConstraint(['snapshot_id'], ['training_snapshots.snapshot_id']),
        sa.ForeignKeyConstraint(['evaluation_id'], ['model_evaluations.evaluation_id']),
        sa.PrimaryKeyConstraint('approval_id'),
        sa.UniqueConstraint('evaluation_id'),
    )
    op.create_index('ix_model_approvals_model_id', 'model_approvals', ['model_id'])

    op.create_table(
        'model_deployments',
        sa.Column('deployment_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('model_id', sa.String(length=36), nullable=False),
        sa.Column('model_version', sa.String(length=20), nullable=True),
        sa.Column('approval_id', sa.String(length=36), nullable=True),
        sa.Column('evaluation_id', sa.String(length=36), nullable=True),
        sa.Column('snapshot_id', sa.Integer(), nullable=True),
        sa.Column('weights_sha256', sa.String(length=64), nullable=False),
        sa.Column('artifact_file', sa.String(length=255), nullable=True),
        sa.Column('previous_model_id', sa.String(length=36), nullable=True),
        sa.Column('previous_sha256', sa.String(length=64), nullable=True),
        sa.Column('previous_artifact_file', sa.String(length=255), nullable=True),
        sa.Column('serving_switched', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('requested_by', sa.String(length=36), nullable=True),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('replaced_by', sa.String(length=36), nullable=True),
        sa.Column('lease_token', sa.String(length=36), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('inflight', sa.String(length=16), nullable=True),
        sa.PrimaryKeyConstraint('deployment_id'),
        sa.UniqueConstraint('inflight'),
    )
    op.create_index('ix_model_deployments_status', 'model_deployments', ['status'])
    op.create_index('ix_model_deployments_model_id', 'model_deployments', ['model_id'])

    op.create_table(
        'deployment_events',
        sa.Column('event_id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=40), nullable=False),
        sa.Column('model_id', sa.String(length=36), nullable=True),
        sa.Column('deployment_id', sa.String(length=36), nullable=True),
        sa.Column('approval_id', sa.String(length=36), nullable=True),
        sa.Column('actor_id', sa.String(length=36), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('event_id'),
    )
    op.create_index('ix_deployment_events_event_type', 'deployment_events', ['event_type'])
    op.create_index('ix_deployment_events_model_id', 'deployment_events', ['model_id'])
    op.create_index('ix_deployment_events_deployment_id', 'deployment_events', ['deployment_id'])


def downgrade():
    op.drop_index('ix_deployment_events_deployment_id', table_name='deployment_events')
    op.drop_index('ix_deployment_events_model_id', table_name='deployment_events')
    op.drop_index('ix_deployment_events_event_type', table_name='deployment_events')
    op.drop_table('deployment_events')
    op.drop_index('ix_model_deployments_model_id', table_name='model_deployments')
    op.drop_index('ix_model_deployments_status', table_name='model_deployments')
    op.drop_table('model_deployments')
    op.drop_index('ix_model_approvals_model_id', table_name='model_approvals')
    op.drop_table('model_approvals')
