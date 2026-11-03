"""v1.1.0 Block A2.1: worker ownership and leases for snapshot training jobs

Additive only.

Revision ID: c3e4f5a6b7d8
Revises: b2d3e4f5a6c7
Create Date: 2026-10-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3e4f5a6b7d8'
down_revision = 'b2d3e4f5a6c7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('training_jobs', sa.Column('worker_id', sa.String(length=128), nullable=True))
    op.add_column('training_jobs', sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('training_jobs', sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('training_jobs', sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for col in ('heartbeat_at', 'lease_expires_at', 'attempt_count', 'worker_id'):
        op.drop_column('training_jobs', col)
