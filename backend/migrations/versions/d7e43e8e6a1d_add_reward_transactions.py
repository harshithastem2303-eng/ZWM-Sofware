"""add_reward_transactions

Revision ID: d7e43e8e6a1d
Revises: 2942998adb44
Create Date: 2026-08-24 11:45:11.548077

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7e43e8e6a1d'
down_revision = '2942998adb44'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'reward_transactions',
        sa.Column('transaction_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('image_id', sa.String(length=36), nullable=True),
        sa.Column('points', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.ForeignKeyConstraint(['image_id'], ['images.image_id']),
        sa.PrimaryKeyConstraint('transaction_id')
    )


def downgrade():
    op.drop_table('reward_transactions')
