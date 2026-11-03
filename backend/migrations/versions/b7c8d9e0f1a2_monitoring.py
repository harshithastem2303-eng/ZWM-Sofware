"""v1.1.0 Block A5: training attempt history, scheduler heartbeats, monitoring indexes

Additive only: two new tables and four indexes on existing timestamp columns.
No existing row is modified.

Revision ID: b7c8d9e0f1a2
Revises: f6b7c8d9e0a1
Create Date: 2026-10-28 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c8d9e0f1a2'
down_revision = 'f6b7c8d9e0a1'
branch_labels = None
depends_on = None

_TIME_INDEXES = (
    ('ix_training_jobs_created_at', 'training_jobs', 'created_at'),
    ('ix_model_evaluations_created_at', 'model_evaluations', 'created_at'),
    ('ix_model_deployments_requested_at', 'model_deployments', 'requested_at'),
    ('ix_deployment_events_created_at', 'deployment_events', 'created_at'),
)


def upgrade():
    op.create_table(
        'training_job_events',
        sa.Column('event_id', sa.String(length=36), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('status_before', sa.String(length=20), nullable=True),
        sa.Column('status_after', sa.String(length=20), nullable=True),
        sa.Column('attempt', sa.Integer(), nullable=True),
        sa.Column('dispatch_attempts', sa.Integer(), nullable=True),
        sa.Column('worker_id', sa.String(length=128), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('event_id'),
    )
    op.create_index('ix_training_job_events_job_id', 'training_job_events', ['job_id'])
    op.create_index('ix_training_job_events_created_at', 'training_job_events', ['created_at'])

    op.create_table(
        'scheduler_heartbeats',
        sa.Column('job_name', sa.String(length=64), nullable=False),
        sa.Column('interval_seconds', sa.Integer(), nullable=False),
        sa.Column('process_id', sa.String(length=128), nullable=True),
        sa.Column('last_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_status', sa.String(length=16), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('last_duration_seconds', sa.Float(), nullable=True),
        sa.Column('run_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('job_name'),
    )
    for name, table, column in _TIME_INDEXES:
        op.create_index(name, table, [column])


def downgrade():
    for name, table, _ in reversed(_TIME_INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_table('scheduler_heartbeats')
    op.drop_index('ix_training_job_events_created_at', table_name='training_job_events')
    op.drop_index('ix_training_job_events_job_id', table_name='training_job_events')
    op.drop_table('training_job_events')
