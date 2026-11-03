"""v1.1.0 Block A6.1: immutable prediction provenance

Additive only: one new append-only table, prediction_records, plus (PostgreSQL) a
trigger refusing UPDATE/DELETE on it. No existing table or row is modified and no
historical prediction is fabricated (none were stored before A6.1).

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-11-02 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from app.models.prediction import PREDICTION_GUARD_FUNCTION_SQL, PREDICTION_GUARD_TRIGGER_SQL


# revision identifiers, used by Alembic.
revision = 'e0f1a2b3c4d5'
down_revision = 'd9e0f1a2b3c4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'prediction_records',
        sa.Column('prediction_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('image_id', sa.String(length=36), nullable=True),
        sa.Column('requested_by', sa.String(length=36), nullable=True),
        sa.Column('environment', sa.String(length=32), nullable=False),
        sa.Column('model_kind', sa.String(length=32), nullable=False),
        sa.Column('attribution', sa.String(length=32), nullable=False),
        sa.Column('model_sha256', sa.String(length=64), nullable=True),
        sa.Column('model_artifact', sa.String(length=255), nullable=True),
        sa.Column('inference_backend', sa.String(length=16), nullable=True),
        sa.Column('inference_engine', sa.String(length=64), nullable=True),
        sa.Column('model_version_id', sa.String(length=36), nullable=True),
        sa.Column('model_version', sa.String(length=20), nullable=True),
        sa.Column('deployment_id', sa.String(length=36), nullable=True),
        sa.Column('snapshot_id', sa.Integer(), nullable=True),
        sa.Column('class_map_sha256', sa.String(length=64), nullable=True),
        sa.Column('class_names', sa.JSON(), nullable=True),
        sa.Column('detection_count', sa.Integer(), nullable=False),
        sa.Column('detections', sa.JSON(), nullable=False),
        sa.Column('confidence_is_model_score', sa.Boolean(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('request_params', sa.JSON(), nullable=True),
        sa.Column('error', sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint('prediction_id'),
    )
    op.create_index('ix_prediction_records_created_at', 'prediction_records', ['created_at'])
    op.create_index('ix_prediction_records_image_id', 'prediction_records', ['image_id'])
    op.create_index('ix_prediction_records_model_version_id', 'prediction_records', ['model_version_id'])
    op.create_index('ix_prediction_records_deployment_id', 'prediction_records', ['deployment_id'])
    op.create_index('ix_prediction_records_requested_by_created', 'prediction_records',
                    ['requested_by', 'created_at'])
    if op.get_bind().dialect.name == 'postgresql':
        op.execute(PREDICTION_GUARD_FUNCTION_SQL)
        op.execute(PREDICTION_GUARD_TRIGGER_SQL)


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP TRIGGER IF EXISTS trg_prediction_records_append_only ON prediction_records")
        op.execute("DROP FUNCTION IF EXISTS zwm_guard_prediction_records()")
    for name in ('ix_prediction_records_requested_by_created', 'ix_prediction_records_deployment_id',
                 'ix_prediction_records_model_version_id', 'ix_prediction_records_image_id',
                 'ix_prediction_records_created_at'):
        op.drop_index(name, table_name='prediction_records')
    op.drop_table('prediction_records')
