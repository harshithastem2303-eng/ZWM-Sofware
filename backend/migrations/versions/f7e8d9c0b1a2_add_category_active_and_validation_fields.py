"""Add is_active, description, created_at to categories; add validation and review fields to images

Revision ID: f7e8d9c0b1a2
Revises: d7e43e8e6a1d
Create Date: 2026-08-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7e8d9c0b1a2'
down_revision = 'd7e43e8e6a1d'
branch_labels = None
depends_on = None


def upgrade():
    # Category table additions
    op.add_column('categories', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('categories', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('categories', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))

    # Image table additions
    op.add_column('images', sa.Column('selected_category_id', sa.Integer(), sa.ForeignKey('categories.category_id'), nullable=True))
    op.add_column('images', sa.Column('ai_predicted_category', sa.String(length=50), nullable=True))
    op.add_column('images', sa.Column('ai_confidence_score', sa.Float(), nullable=True))
    op.add_column('images', sa.Column('validation_result', sa.String(length=50), nullable=True))
    op.add_column('images', sa.Column('validation_reason', sa.Text(), nullable=True))
    op.add_column('images', sa.Column('reviewed_by', sa.String(length=36), sa.ForeignKey('users.user_id'), nullable=True))
    op.add_column('images', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('images', 'reviewed_at')
    op.drop_column('images', 'reviewed_by')
    op.drop_column('images', 'validation_reason')
    op.drop_column('images', 'validation_result')
    op.drop_column('images', 'ai_confidence_score')
    op.drop_column('images', 'ai_predicted_category')
    op.drop_column('images', 'selected_category_id')

    op.drop_column('categories', 'created_at')
    op.drop_column('categories', 'is_active')
    op.drop_column('categories', 'description')
