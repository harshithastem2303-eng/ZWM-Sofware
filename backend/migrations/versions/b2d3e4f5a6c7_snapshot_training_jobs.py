"""v1.1.0 Block A2: link training jobs to snapshots (durable outbox for automatic training)

Additive only — existing training_jobs rows become legacy/manual jobs
(snapshot_id NULL, trigger 'manual'), behaviour unchanged.

Revision ID: b2d3e4f5a6c7
Revises: a1c2e3f4b5d6
Create Date: 2026-10-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2d3e4f5a6c7'
down_revision = 'a1c2e3f4b5d6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('training_jobs', sa.Column('snapshot_id', sa.Integer(), nullable=True))
    op.add_column('training_jobs', sa.Column('trigger', sa.String(length=20), nullable=False, server_default='manual'))
    op.add_column('training_jobs', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('training_jobs', sa.Column('dataset_status', sa.String(length=20), nullable=True))
    op.add_column('training_jobs', sa.Column('dataset_manifest_path', sa.Text(), nullable=True))
    op.add_column('training_jobs', sa.Column('error_message', sa.Text(), nullable=True))
    op.add_column('training_jobs', sa.Column('dispatched_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('training_jobs', sa.Column('dispatch_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('training_jobs', sa.Column('celery_task_id', sa.String(length=64), nullable=True))
    op.create_foreign_key(
        'fk_training_jobs_snapshot_id', 'training_jobs', 'training_snapshots',
        ['snapshot_id'], ['snapshot_id'],
    )
    op.create_unique_constraint('uq_training_jobs_snapshot_id', 'training_jobs', ['snapshot_id'])


def downgrade():
    op.drop_constraint('uq_training_jobs_snapshot_id', 'training_jobs', type_='unique')
    op.drop_constraint('fk_training_jobs_snapshot_id', 'training_jobs', type_='foreignkey')
    for col in ('celery_task_id', 'dispatch_attempts', 'dispatched_at', 'error_message',
                'dataset_manifest_path', 'dataset_status', 'created_at', 'trigger', 'snapshot_id'):
        op.drop_column('training_jobs', col)
