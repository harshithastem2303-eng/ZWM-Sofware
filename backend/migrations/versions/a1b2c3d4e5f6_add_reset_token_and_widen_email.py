"""Add password_reset_token, reset_token_expiry to users; widen email columns

Revision ID: a1b2c3d4e5f6
Revises: 067a102509dc
Create Date: 2026-08-19 10:45:00.000000

Changes:
  - users.email: String(30) -> String(255)
  - users.password_reset_token: new nullable Text column
  - users.reset_token_expiry: new nullable DateTime(timezone=True) column
  - admins.admin_email: String(30) -> String(255)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '067a102509dc'
branch_labels = None
depends_on = None


def upgrade():
    # Widen users.email from 30 to 255 characters
    op.alter_column(
        'users',
        'email',
        existing_type=sa.String(length=30),
        type_=sa.String(length=255),
        existing_nullable=False,
    )

    # Add dedicated password-reset fields to users
    op.add_column(
        'users',
        sa.Column('password_reset_token', sa.Text(), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column('reset_token_expiry', sa.DateTime(timezone=True), nullable=True),
    )

    # Widen admins.admin_email from 30 to 255 characters
    op.alter_column(
        'admins',
        'admin_email',
        existing_type=sa.String(length=30),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade():
    # Remove reset token fields
    op.drop_column('users', 'reset_token_expiry')
    op.drop_column('users', 'password_reset_token')

    # Narrow email columns back (may fail if existing data exceeds 30 chars)
    op.alter_column(
        'users',
        'email',
        existing_type=sa.String(length=255),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
    op.alter_column(
        'admins',
        'admin_email',
        existing_type=sa.String(length=255),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
