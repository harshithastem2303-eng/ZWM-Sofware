"""v1.1.0 Block A3: candidate model evaluations and admin quality-gate policy

Additive only. evaluation_policies starts EMPTY: no thresholds are assumed until
an administrator configures them.

Revision ID: d4f5a6b7c8e9
Revises: c3e4f5a6b7d8
Create Date: 2026-10-26 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4f5a6b7c8e9'
down_revision = 'c3e4f5a6b7d8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'model_evaluations',
        sa.Column('evaluation_id', sa.String(length=36), nullable=False),
        sa.Column('model_id', sa.String(length=36), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=False),
        sa.Column('config_hash', sa.String(length=64), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('gate_decision', sa.String(length=32), nullable=True),
        sa.Column('weights_path', sa.Text(), nullable=False),
        sa.Column('weights_sha256', sa.String(length=64), nullable=False),
        sa.Column('dataset_manifest_path', sa.Text(), nullable=False),
        sa.Column('model_version', sa.String(length=20), nullable=True),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('gate_results', sa.JSON(), nullable=True),
        sa.Column('baseline', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('test_image_count', sa.Integer(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('requested_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dispatched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dispatch_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('worker_id', sa.String(length=128), nullable=True),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['model_id'], ['model_versions.model_id']),
        sa.ForeignKeyConstraint(['job_id'], ['training_jobs.job_id']),
        sa.ForeignKeyConstraint(['snapshot_id'], ['training_snapshots.snapshot_id']),
        sa.PrimaryKeyConstraint('evaluation_id'),
        sa.UniqueConstraint('model_id', 'config_hash', name='uq_model_evaluations_model_config'),
    )
    op.create_index('ix_model_evaluations_model_id', 'model_evaluations', ['model_id'])
    op.create_index('ix_model_evaluations_status', 'model_evaluations', ['status'])

    op.create_table(
        'evaluation_policies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('min_test_images', sa.Integer(), nullable=True),
        sa.Column('min_objects_per_class', sa.Integer(), nullable=True),
        sa.Column('require_class_coverage', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('min_map50', sa.Float(), nullable=True),
        sa.Column('min_map50_95', sa.Float(), nullable=True),
        sa.Column('min_precision', sa.Float(), nullable=True),
        sa.Column('min_recall', sa.Float(), nullable=True),
        sa.Column('min_class_recall', sa.Float(), nullable=True),
        sa.Column('max_map50_regression', sa.Float(), nullable=True),
        sa.Column('updated_by', sa.String(length=36), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('evaluation_policies')
    op.drop_index('ix_model_evaluations_status', table_name='model_evaluations')
    op.drop_index('ix_model_evaluations_model_id', table_name='model_evaluations')
    op.drop_table('model_evaluations')
