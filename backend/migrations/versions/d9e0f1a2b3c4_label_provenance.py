"""v1.1.0 Block A6.0 completion: label provenance and server-side AI-suggestion evidence

Additive only:
  * images.label_provenance (user_confirmed | admin_approved; NULL for every existing
    row -- nothing is backfilled or re-validated);
  * images.ai_suggested_at (set when AI suggestions were served for the image);
  * PostgreSQL: zwm_guard_training_eligibility() is replaced by the V2 body, which
    also accepts a user-confirmed, human-only revision (A1 finalization) besides an
    administrator approval. The trigger itself is unchanged.
Existing training sequences, snapshots and label reviews are not modified.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-11-02 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from app.models.label_review import TRAINING_GATE_FUNCTION_SQL, TRAINING_GATE_FUNCTION_SQL_V2


# revision identifiers, used by Alembic.
revision = 'd9e0f1a2b3c4'
down_revision = 'c8d9e0f1a2b3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('images', sa.Column('label_provenance', sa.String(length=20), nullable=True))
    op.add_column('images', sa.Column('ai_suggested_at', sa.DateTime(timezone=True), nullable=True))
    if op.get_bind().dialect.name == 'postgresql':
        op.execute(TRAINING_GATE_FUNCTION_SQL_V2)


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute(TRAINING_GATE_FUNCTION_SQL)          # A6.0 (mandatory approval) body
    op.drop_column('images', 'ai_suggested_at')
    op.drop_column('images', 'label_provenance')
