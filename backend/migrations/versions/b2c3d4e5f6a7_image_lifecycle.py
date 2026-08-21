"""Add image lifecycle columns: storage_type, temporary_expires_at, annotated_at,
converted_at, permanent_at, yolo_txt_path; add performance indexes.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-19 18:08:00.000000

Changes:
  - images.storage_type:          new VARCHAR(20) column, default 'local'
  - images.temporary_expires_at:  new TIMESTAMP WITH TIME ZONE column (nullable)
  - images.annotated_at:          new TIMESTAMP WITH TIME ZONE column (nullable)
  - images.converted_at:          new TIMESTAMP WITH TIME ZONE column (nullable)
  - images.permanent_at:          new TIMESTAMP WITH TIME ZONE column (nullable)
  - images.yolo_txt_path:         new TEXT column (nullable)
  - Index on images.status
  - Index on images.temporary_expires_at
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # -- Add new lifecycle columns to images table ---------------------------
    op.add_column(
        'images',
        sa.Column('storage_type', sa.String(length=20), nullable=True, server_default='local'),
    )
    op.add_column(
        'images',
        sa.Column('temporary_expires_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'images',
        sa.Column('annotated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'images',
        sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'images',
        sa.Column('permanent_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'images',
        sa.Column('yolo_txt_path', sa.Text(), nullable=True),
    )

    # -- Indexes for efficient lifecycle queries ------------------------------
    op.create_index(
        'ix_images_status',
        'images',
        ['status'],
    )
    op.create_index(
        'ix_images_temporary_expires_at',
        'images',
        ['temporary_expires_at'],
    )


def downgrade():
    op.drop_index('ix_images_temporary_expires_at', table_name='images')
    op.drop_index('ix_images_status', table_name='images')

    op.drop_column('images', 'yolo_txt_path')
    op.drop_column('images', 'permanent_at')
    op.drop_column('images', 'converted_at')
    op.drop_column('images', 'annotated_at')
    op.drop_column('images', 'temporary_expires_at')
    op.drop_column('images', 'storage_type')
