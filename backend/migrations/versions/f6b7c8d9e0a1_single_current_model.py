"""v1.1.0 Block A4.1: database-enforced single current model + activation guard trigger

* uq_model_versions_single_current: partial UNIQUE index, at most one row with
  is_current = true (covers bulk UPDATEs and raw SQL).
* PostgreSQL trigger zwm_guard_snapshot_activation: a snapshot-trained candidate
  can only become current inside a transaction authorised by the A4 deployment
  service (set_config('zwm.allow_current_change', 'on', true)).

The upgrade never modifies data. If more than one model is already current it
stops with an explicit error listing them; an operator must resolve that first.

Revision ID: f6b7c8d9e0a1
Revises: e5a6b7c8d9f0
Create Date: 2026-10-27 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6b7c8d9e0a1'
down_revision = 'e5a6b7c8d9f0'
branch_labels = None
depends_on = None


def upgrade():
    from app.models.training import ACTIVATION_GUARD_FUNCTION_SQL, ACTIVATION_GUARD_TRIGGER_SQL

    bind = op.get_bind()
    current = [r[0] for r in bind.execute(sa.text(
        "SELECT model_id FROM model_versions WHERE is_current IS TRUE ORDER BY model_id")).fetchall()]
    if len(current) > 1:
        raise RuntimeError(
            "Block A4.1 migration stopped: %d model versions are marked current (%s). "
            "Exactly one (or none) may be current. Decide which model is really serving, "
            "clear is_current on the others, then re-run the upgrade. No data was changed."
            % (len(current), ", ".join(current))
        )
    op.create_index(
        'uq_model_versions_single_current', 'model_versions', ['is_current'], unique=True,
        postgresql_where=sa.text('is_current'), sqlite_where=sa.text('is_current = 1'),
    )
    if bind.dialect.name == 'postgresql':
        op.execute(ACTIVATION_GUARD_FUNCTION_SQL)
        op.execute("DROP TRIGGER IF EXISTS trg_model_versions_activation_guard ON model_versions")
        op.execute(ACTIVATION_GUARD_TRIGGER_SQL)


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP TRIGGER IF EXISTS trg_model_versions_activation_guard ON model_versions")
        op.execute("DROP FUNCTION IF EXISTS zwm_guard_snapshot_activation()")
    op.drop_index('uq_model_versions_single_current', table_name='model_versions')
