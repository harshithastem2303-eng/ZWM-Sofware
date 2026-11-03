"""v1.1.0 Block A6.0: human label review evidence and training-eligibility gate

Additive only:
  * images: label_sha256, label_fingerprint, label_finalized_at, label_finalized_by,
    training_review_id (all NULL for existing rows -- no approval is backfilled);
  * label_reviews: append-only administrator decisions on exact label revisions;
  * PostgreSQL triggers: label_reviews immutability + reviewer independence, and
    images.training_sequence may only go NULL -> value with a matching approval;
    annotations of an eligible image cannot be inserted/updated/deleted (row-locked check).
Existing training sequences, snapshots and their contents are not modified.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-10-30 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from app.models.label_review import (
    ANNOTATION_LOCK_FUNCTION_SQL,
    ANNOTATION_LOCK_TRIGGER_SQL,
    LABEL_REVIEW_GUARD_FUNCTION_SQL,
    LABEL_REVIEW_GUARD_TRIGGER_SQL,
    TRAINING_GATE_FUNCTION_SQL,
    TRAINING_GATE_TRIGGER_SQL,
)


# revision identifiers, used by Alembic.
revision = 'c8d9e0f1a2b3'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None

_IMAGE_COLUMNS = (
    sa.Column('label_sha256', sa.String(length=64), nullable=True),
    sa.Column('label_fingerprint', sa.String(length=64), nullable=True),
    sa.Column('label_finalized_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('label_finalized_by', sa.String(length=36), nullable=True),
    sa.Column('training_review_id', sa.String(length=36), nullable=True),
)


def upgrade():
    for col in _IMAGE_COLUMNS:
        op.add_column('images', col.copy())
    op.create_table(
        'label_reviews',
        sa.Column('review_id', sa.String(length=36), nullable=False),
        sa.Column('image_id', sa.String(length=36), nullable=False),
        sa.Column('label_sha256', sa.String(length=64), nullable=False),
        sa.Column('annotation_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('outcome', sa.String(length=16), nullable=False),
        sa.Column('reviewer_id', sa.String(length=36), nullable=False),
        sa.Column('reviewer_email', sa.String(length=255), nullable=True),
        sa.Column('annotator_ids', sa.JSON(), nullable=False),
        sa.Column('ai_involved', sa.Boolean(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('review_id'),
    )
    op.create_index('ix_label_reviews_image_id', 'label_reviews', ['image_id'])
    op.create_index('uq_label_reviews_approved_revision', 'label_reviews',
                    ['image_id', 'label_sha256', 'annotation_fingerprint'], unique=True,
                    postgresql_where=sa.text("outcome = 'approved'"))
    if op.get_bind().dialect.name == 'postgresql':
        op.execute(LABEL_REVIEW_GUARD_FUNCTION_SQL)
        op.execute(LABEL_REVIEW_GUARD_TRIGGER_SQL)
        op.execute(TRAINING_GATE_FUNCTION_SQL)
        op.execute(TRAINING_GATE_TRIGGER_SQL)
        op.execute(ANNOTATION_LOCK_FUNCTION_SQL)
        op.execute(ANNOTATION_LOCK_TRIGGER_SQL)


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP TRIGGER IF EXISTS trg_annotations_training_lock ON annotations")
        op.execute("DROP FUNCTION IF EXISTS zwm_guard_eligible_annotations()")
        op.execute("DROP TRIGGER IF EXISTS trg_images_training_gate ON images")
        op.execute("DROP FUNCTION IF EXISTS zwm_guard_training_eligibility()")
        op.execute("DROP TRIGGER IF EXISTS trg_label_reviews_guard ON label_reviews")
        op.execute("DROP FUNCTION IF EXISTS zwm_guard_label_reviews()")
    op.drop_index('uq_label_reviews_approved_revision', table_name='label_reviews')
    op.drop_index('ix_label_reviews_image_id', table_name='label_reviews')
    op.drop_table('label_reviews')
    for col in reversed(_IMAGE_COLUMNS):
        op.drop_column('images', col.name)
