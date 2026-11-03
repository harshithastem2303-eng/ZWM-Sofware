"""v1.1.0 Block A6.3: immutable label revisions and governed feedback corrections

Additive only: label_revisions (immutable contents), label_revision_events
(append-only lifecycle) and label_revision_heads (the only mutable row: each image's
current revision pointer), plus (PostgreSQL) guard triggers. No existing table or row
is modified; images, annotations, label_reviews, training snapshots, prediction
records and feedback are only referenced.

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e7
Create Date: 2026-11-03 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from app.models.label_revision import (
    EVENT_GUARD_FUNCTION_SQL,
    EVENT_GUARD_TRIGGER_SQL,
    HEAD_GUARD_FUNCTION_SQL,
    HEAD_GUARD_TRIGGER_SQL,
    REVISION_GUARD_FUNCTION_SQL,
    REVISION_GUARD_TRIGGER_SQL,
)


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = 'f1a2b3c4d5e7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'label_revisions',
        sa.Column('revision_id', sa.String(length=36), nullable=False),
        sa.Column('image_id', sa.String(length=36), nullable=False),
        sa.Column('revision_number', sa.Integer(), nullable=False),
        sa.Column('parent_revision_id', sa.String(length=36), nullable=True),
        sa.Column('source', sa.String(length=24), nullable=False),
        sa.Column('feedback_id', sa.String(length=36), nullable=True),
        sa.Column('feedback_decision_id', sa.String(length=36), nullable=True),
        sa.Column('prediction_id', sa.String(length=36), nullable=True),
        sa.Column('created_by', sa.String(length=36), nullable=False),
        sa.Column('created_by_email', sa.String(length=255), nullable=True),
        sa.Column('created_by_role', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('contents', sa.JSON(), nullable=False),
        sa.Column('object_count', sa.Integer(), nullable=False),
        sa.Column('correction', sa.JSON(), nullable=True),
        sa.Column('class_map', sa.JSON(), nullable=False),
        sa.Column('class_map_sha256', sa.String(length=64), nullable=False),
        sa.Column('content_sha256', sa.String(length=64), nullable=False),
        sa.Column('annotation_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('label_text', sa.Text(), nullable=False),
        sa.Column('label_sha256', sa.String(length=64), nullable=False),
        sa.Column('base_label_sha256', sa.String(length=64), nullable=True),
        sa.Column('base_training_sequence', sa.Integer(), nullable=True),
        sa.Column('base_training_review_id', sa.String(length=36), nullable=True),
        sa.Column('base_label_provenance', sa.String(length=20), nullable=True),
        sa.Column('installed_label_sha256', sa.String(length=64), nullable=True),
        sa.Column('installed_label_text', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['parent_revision_id'], ['label_revisions.revision_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['feedback_id'], ['prediction_feedback.feedback_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['feedback_decision_id'], ['prediction_feedback_decisions.decision_id'],
                                ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['prediction_id'], ['prediction_records.prediction_id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('revision_id'),
    )
    op.create_index('ix_label_revisions_image_id', 'label_revisions', ['image_id'])
    op.create_index('uq_label_revisions_image_number', 'label_revisions', ['image_id', 'revision_number'],
                    unique=True)
    op.create_index('uq_label_revisions_feedback', 'label_revisions', ['feedback_id'], unique=True,
                    postgresql_where=sa.text("feedback_id IS NOT NULL"),
                    sqlite_where=sa.text("feedback_id IS NOT NULL"))

    op.create_table(
        'label_revision_events',
        sa.Column('event_id', sa.String(length=36), nullable=False),
        sa.Column('revision_id', sa.String(length=36), nullable=False),
        sa.Column('image_id', sa.String(length=36), nullable=False),
        sa.Column('event', sa.String(length=16), nullable=False),
        sa.Column('from_status', sa.String(length=16), nullable=True),
        sa.Column('to_status', sa.String(length=16), nullable=False),
        sa.Column('actor_id', sa.String(length=36), nullable=False),
        sa.Column('actor_email', sa.String(length=255), nullable=True),
        sa.Column('actor_role', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['revision_id'], ['label_revisions.revision_id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('event_id'),
    )
    op.create_index('uq_label_revision_events_once', 'label_revision_events', ['revision_id', 'event'],
                    unique=True)
    op.create_index('uq_label_revision_events_decision', 'label_revision_events', ['revision_id'], unique=True,
                    postgresql_where=sa.text("event IN ('approved', 'rejected')"),
                    sqlite_where=sa.text("event IN ('approved', 'rejected')"))
    op.create_index('ix_label_revision_events_image', 'label_revision_events', ['image_id', 'created_at'])

    op.create_table(
        'label_revision_heads',
        sa.Column('image_id', sa.String(length=36), nullable=False),
        sa.Column('revision_id', sa.String(length=36), nullable=False),
        sa.Column('event_id', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['revision_id'], ['label_revisions.revision_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['event_id'], ['label_revision_events.event_id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('image_id'),
    )

    if op.get_bind().dialect.name == 'postgresql':
        for sql in (REVISION_GUARD_FUNCTION_SQL, REVISION_GUARD_TRIGGER_SQL, EVENT_GUARD_FUNCTION_SQL,
                    EVENT_GUARD_TRIGGER_SQL, HEAD_GUARD_FUNCTION_SQL, HEAD_GUARD_TRIGGER_SQL):
            op.execute(sql)


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        for table, trigger, function in (
                ('label_revision_heads', 'trg_label_revision_heads_guard', 'zwm_guard_label_revision_heads'),
                ('label_revision_events', 'trg_label_revision_events_guard', 'zwm_guard_label_revision_events'),
                ('label_revisions', 'trg_label_revisions_guard', 'zwm_guard_label_revisions')):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
            op.execute(f"DROP FUNCTION IF EXISTS {function}()")
    op.drop_table('label_revision_heads')
    for name in ('ix_label_revision_events_image', 'uq_label_revision_events_decision',
                 'uq_label_revision_events_once'):
        op.drop_index(name, table_name='label_revision_events')
    op.drop_table('label_revision_events')
    for name in ('uq_label_revisions_feedback', 'uq_label_revisions_image_number', 'ix_label_revisions_image_id'):
        op.drop_index(name, table_name='label_revisions')
    op.drop_table('label_revisions')
