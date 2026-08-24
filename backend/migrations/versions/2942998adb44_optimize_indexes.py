"""optimize_indexes

Revision ID: 2942998adb44
Revises: c3d4e5f6a7b8
Create Date: 2026-08-24 11:18:05.199254

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2942998adb44'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    # -- Create index on annotations.image_id --------------------------------
    op.create_index(
        'ix_annotations_image_id',
        'annotations',
        ['image_id'],
        unique=False,
    )

    # -- Create composite index on images(user_id, uploaded_at) --------------
    op.create_index(
        'ix_images_user_id_uploaded_at',
        'images',
        ['user_id', 'uploaded_at'],
        unique=False,
    )

    # -- Create index on training_jobs.status --------------------------------
    op.create_index(
        'ix_training_jobs_status',
        'training_jobs',
        ['status'],
        unique=False,
    )

    # -- Create index on model_versions.is_current ---------------------------
    op.create_index(
        'ix_model_versions_is_current',
        'model_versions',
        ['is_current'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_model_versions_is_current', table_name='model_versions')
    op.drop_index('ix_training_jobs_status', table_name='training_jobs')
    op.drop_index('ix_images_user_id_uploaded_at', table_name='images')
    op.drop_index('ix_annotations_image_id', table_name='annotations')
