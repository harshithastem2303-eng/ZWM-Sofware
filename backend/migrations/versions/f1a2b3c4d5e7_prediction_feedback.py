"""v1.1.0 Block A6.2: prediction feedback and administrator review

Additive only: two new tables, prediction_feedback and prediction_feedback_decisions,
plus (PostgreSQL) triggers enforcing the pending -> approved | rejected lifecycle,
append-only decisions and independent review. No existing table or row is modified;
prediction_records stays untouched (only referenced).

Revision ID: f1a2b3c4d5e7
Revises: e0f1a2b3c4d5
Create Date: 2026-11-02 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from app.models.feedback import (
    DECISION_GUARD_FUNCTION_SQL,
    DECISION_GUARD_TRIGGER_SQL,
    FEEDBACK_GUARD_FUNCTION_SQL,
    FEEDBACK_GUARD_TRIGGER_SQL,
)


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e7'
down_revision = 'e0f1a2b3c4d5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'prediction_feedback',
        sa.Column('feedback_id', sa.String(length=36), nullable=False),
        sa.Column('prediction_id', sa.String(length=36), nullable=False),
        sa.Column('submitted_by', sa.String(length=36), nullable=False),
        sa.Column('submitter_role', sa.String(length=20), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('environment', sa.String(length=32), nullable=False),
        sa.Column('feedback_type', sa.String(length=32), nullable=False),
        sa.Column('target', sa.String(length=24), nullable=False),
        sa.Column('detection_index', sa.Integer(), nullable=True),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('suggested_category_id', sa.Integer(), nullable=True),
        sa.Column('suggested_class_name', sa.String(length=50), nullable=True),
        sa.Column('suggested_yolo_class_index', sa.Integer(), nullable=True),
        sa.Column('suggested_geometry', sa.JSON(), nullable=True),
        sa.Column('image_id', sa.String(length=36), nullable=True),
        sa.Column('prediction_source', sa.String(length=32), nullable=False),
        sa.Column('model_kind', sa.String(length=32), nullable=False),
        sa.Column('model_attribution', sa.String(length=32), nullable=False),
        sa.Column('model_sha256', sa.String(length=64), nullable=True),
        sa.Column('model_version_id', sa.String(length=36), nullable=True),
        sa.Column('deployment_id', sa.String(length=36), nullable=True),
        sa.Column('original_detection', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(['prediction_id'], ['prediction_records.prediction_id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('feedback_id'),
    )
    op.create_index('ix_prediction_feedback_prediction_id', 'prediction_feedback', ['prediction_id'])
    op.create_index('ix_prediction_feedback_image_id', 'prediction_feedback', ['image_id'])
    op.create_index('ix_prediction_feedback_status_submitted', 'prediction_feedback', ['status', 'submitted_at'])
    op.create_index('ix_prediction_feedback_submitter_submitted', 'prediction_feedback',
                    ['submitted_by', 'submitted_at'])
    op.create_index('uq_prediction_feedback_open', 'prediction_feedback',
                    ['prediction_id', 'submitted_by', 'feedback_type', 'target'], unique=True,
                    postgresql_where=sa.text("status IN ('pending', 'approved')"),
                    sqlite_where=sa.text("status IN ('pending', 'approved')"))

    op.create_table(
        'prediction_feedback_decisions',
        sa.Column('decision_id', sa.String(length=36), nullable=False),
        sa.Column('feedback_id', sa.String(length=36), nullable=False),
        sa.Column('decision', sa.String(length=16), nullable=False),
        sa.Column('reviewer_id', sa.String(length=36), nullable=False),
        sa.Column('reviewer_email', sa.String(length=255), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('previous_status', sa.String(length=16), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['feedback_id'], ['prediction_feedback.feedback_id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('decision_id'),
        sa.UniqueConstraint('feedback_id'),
    )

    if op.get_bind().dialect.name == 'postgresql':
        op.execute(FEEDBACK_GUARD_FUNCTION_SQL)
        op.execute(FEEDBACK_GUARD_TRIGGER_SQL)
        op.execute(DECISION_GUARD_FUNCTION_SQL)
        op.execute(DECISION_GUARD_TRIGGER_SQL)


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP TRIGGER IF EXISTS trg_feedback_decisions_guard ON prediction_feedback_decisions")
        op.execute("DROP FUNCTION IF EXISTS zwm_guard_feedback_decisions()")
        op.execute("DROP TRIGGER IF EXISTS trg_prediction_feedback_guard ON prediction_feedback")
        op.execute("DROP FUNCTION IF EXISTS zwm_guard_prediction_feedback()")
    op.drop_table('prediction_feedback_decisions')
    for name in ('uq_prediction_feedback_open', 'ix_prediction_feedback_submitter_submitted',
                 'ix_prediction_feedback_status_submitted', 'ix_prediction_feedback_image_id',
                 'ix_prediction_feedback_prediction_id'):
        op.drop_index(name, table_name='prediction_feedback')
    op.drop_table('prediction_feedback')
