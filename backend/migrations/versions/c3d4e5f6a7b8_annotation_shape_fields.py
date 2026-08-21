"""Add annotation shape fields: type, label_data_json, ai_generated, image dimensions.
Also relaxes category_id FK to nullable (predefined dropdown, no hardcoded default).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-19 23:32:00.000000

Changes
-------
annotations.annotation_type   : new VARCHAR(20) column, nullable
annotations.label_data_json   : new JSON column, nullable
annotations.ai_generated      : new BOOLEAN column, nullable, default False
annotations.image_width        : new INTEGER column, nullable
annotations.image_height       : new INTEGER column, nullable
annotations.category_id        : ALTER NOT NULL -> nullable (label-only annotations)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers used by Alembic
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    # -- Relax category_id to nullable ----------------------------------------
    op.alter_column(
        'annotations',
        'category_id',
        existing_type=sa.Integer(),
        nullable=True,
    )

    # -- Add new shape annotation columns -------------------------------------
    op.add_column(
        'annotations',
        sa.Column('annotation_type', sa.String(length=20), nullable=True),
    )
    op.add_column(
        'annotations',
        sa.Column('label_data_json', sa.JSON(), nullable=True),
    )
    op.add_column(
        'annotations',
        sa.Column('ai_generated', sa.Boolean(), nullable=True, server_default='false'),
    )
    op.add_column(
        'annotations',
        sa.Column('image_width', sa.Integer(), nullable=True),
    )
    op.add_column(
        'annotations',
        sa.Column('image_height', sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column('annotations', 'image_height')
    op.drop_column('annotations', 'image_width')
    op.drop_column('annotations', 'ai_generated')
    op.drop_column('annotations', 'label_data_json')
    op.drop_column('annotations', 'annotation_type')

    # Restore category_id to NOT NULL
    op.alter_column(
        'annotations',
        'category_id',
        existing_type=sa.Integer(),
        nullable=False,
    )
