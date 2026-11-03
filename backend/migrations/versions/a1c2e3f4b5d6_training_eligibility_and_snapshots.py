"""v1.1.0 Block A1: training eligibility, YOLO class index, cumulative training snapshots

Additive only — no drops, no data loss.

- categories.yolo_class_index   : contiguous YOLO index; backfilled 0..N-1 by category_id
- images.training_eligible_at   : when the image became training eligible
- images.training_sequence      : stable milestone order (unique)
- training_snapshots            : locked cumulative milestones (unique version / milestone_count)
- training_snapshot_images      : exact image membership per snapshot

Existing permanent images are NOT backfilled as eligible: their YOLO TXT files were
written with business class_code as the class id and must be regenerated first.

Revision ID: a1c2e3f4b5d6
Revises: f7e8d9c0b1a2
Create Date: 2026-10-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c2e3f4b5d6'
down_revision = 'f7e8d9c0b1a2'
branch_labels = None
depends_on = None


def upgrade():
    # -- categories.yolo_class_index ---------------------------------------
    op.add_column('categories', sa.Column('yolo_class_index', sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE categories AS c
        SET yolo_class_index = s.idx
        FROM (
            SELECT category_id, ROW_NUMBER() OVER (ORDER BY category_id) - 1 AS idx
            FROM categories
        ) AS s
        WHERE c.category_id = s.category_id
        """
    )
    op.create_unique_constraint('uq_categories_yolo_class_index', 'categories', ['yolo_class_index'])

    # -- images eligibility --------------------------------------------------
    op.add_column('images', sa.Column('training_eligible_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('images', sa.Column('training_sequence', sa.BigInteger(), nullable=True))
    op.create_unique_constraint('uq_images_training_sequence', 'images', ['training_sequence'])

    # -- training_snapshots ----------------------------------------------------
    op.create_table(
        'training_snapshots',
        sa.Column('snapshot_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('threshold', sa.Integer(), nullable=False),
        sa.Column('milestone_count', sa.Integer(), nullable=False),
        sa.Column('dataset_size', sa.Integer(), nullable=False),
        sa.Column('first_sequence', sa.BigInteger(), nullable=True),
        sa.Column('last_sequence', sa.BigInteger(), nullable=True),
        sa.Column('class_map', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='locked'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('snapshot_id'),
        sa.UniqueConstraint('version', name='uq_training_snapshots_version'),
        sa.UniqueConstraint('milestone_count', name='uq_training_snapshots_milestone_count'),
    )

    op.create_table(
        'training_snapshot_images',
        sa.Column('snapshot_id', sa.Integer(), nullable=False),
        sa.Column('image_id', sa.String(length=36), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('training_sequence', sa.BigInteger(), nullable=False),
        sa.Column('split_type', sa.String(length=10), nullable=True),
        sa.ForeignKeyConstraint(['snapshot_id'], ['training_snapshots.snapshot_id']),
        sa.PrimaryKeyConstraint('snapshot_id', 'image_id'),
        sa.UniqueConstraint('snapshot_id', 'position', name='uq_training_snapshot_images_position'),
    )
    op.create_index(
        'ix_training_snapshot_images_image_id', 'training_snapshot_images', ['image_id'], unique=False
    )


def downgrade():
    op.drop_index('ix_training_snapshot_images_image_id', table_name='training_snapshot_images')
    op.drop_table('training_snapshot_images')
    op.drop_table('training_snapshots')
    op.drop_constraint('uq_images_training_sequence', 'images', type_='unique')
    op.drop_column('images', 'training_sequence')
    op.drop_column('images', 'training_eligible_at')
    op.drop_constraint('uq_categories_yolo_class_index', 'categories', type_='unique')
    op.drop_column('categories', 'yolo_class_index')
