import uuid
from datetime import datetime, timezone

from app.database import Base
from sqlalchemy import Column, String, Integer, BigInteger, Float, Boolean, Text, DateTime, ForeignKey, JSON, UniqueConstraint, Index, DDL, event, text
from sqlalchemy.orm import relationship


class TrainingJob(Base):
    __tablename__ = "training_jobs"

    job_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    version = Column(String(20), nullable=False)
    class_counts = Column(JSON, nullable=True)
    status = Column(String(20), default="queued", index=True)
    best_model_path = Column(Text, nullable=True)
    metadata_path = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # -- Snapshot-driven (automatic) training, v1.1.0 Block A2 ------------------
    # NULL snapshot_id = legacy/manual job (unchanged behaviour).
    # UNIQUE snapshot_id = at most one training job per locked snapshot.
    snapshot_id = Column(Integer, ForeignKey("training_snapshots.snapshot_id"), nullable=True, unique=True)
    trigger = Column(String(20), nullable=False, default="manual")  # manual | auto | admin_snapshot
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    # Dataset preparation: pending | prepared | failed
    dataset_status = Column(String(20), nullable=True)
    dataset_manifest_path = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    # Durable outbox for Celery delivery: NULL dispatched_at = not yet handed to the queue.
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    dispatch_attempts = Column(Integer, nullable=False, default=0)
    celery_task_id = Column(String(64), nullable=True)
    # Worker ownership / lease (Block A2.1). attempt_count doubles as fencing token.
    worker_id = Column(String(128), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)

    model_versions = relationship("ModelVersion", backref="training_job", lazy=True)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    # Block A4.1: at most one current model, enforced by the database itself
    # (covers bulk UPDATEs and raw SQL, not only ORM flushes).
    __table_args__ = (
        Index("uq_model_versions_single_current", "is_current", unique=True,
              postgresql_where=text("is_current"), sqlite_where=text("is_current = 1")),
    )

    model_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("training_jobs.job_id"), nullable=False)
    version = Column(String(20), nullable=False)
    is_current = Column(Boolean, default=False, index=True)
    map_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ModelEvaluation(Base):
    """
    Evaluation of one candidate model on its snapshot's held-out TEST split (Block A3).

    status        : pending | running | passed | failed | error
    gate_decision : eligible_for_review | rejected | insufficient_evidence | policy_not_configured
    'passed' only ever means eligible for human review — never activation.
    UNIQUE(model_id, config_hash) makes repeated requests idempotent.
    """
    __tablename__ = "model_evaluations"
    __table_args__ = (UniqueConstraint("model_id", "config_hash", name="uq_model_evaluations_model_config"),)

    evaluation_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    model_id = Column(String(36), ForeignKey("model_versions.model_id"), nullable=False, index=True)
    job_id = Column(String(36), ForeignKey("training_jobs.job_id"), nullable=False)
    snapshot_id = Column(Integer, ForeignKey("training_snapshots.snapshot_id"), nullable=False)
    config_hash = Column(String(64), nullable=False)
    config = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    gate_decision = Column(String(32), nullable=True)
    weights_path = Column(Text, nullable=False)
    weights_sha256 = Column(String(64), nullable=False)
    dataset_manifest_path = Column(Text, nullable=False)
    model_version = Column(String(20), nullable=True)
    metrics = Column(JSON, nullable=True)
    gate_results = Column(JSON, nullable=True)
    baseline = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    test_image_count = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    requested_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    evaluated_at = Column(DateTime(timezone=True), nullable=True)
    # Durable dispatch + worker lease (same pattern as snapshot training jobs)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    dispatch_attempts = Column(Integer, nullable=False, default=0)
    worker_id = Column(String(128), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)


class EvaluationPolicy(Base):
    """
    Admin-configured quality gates (single row, id=1). Every threshold is NULL by
    default: until an admin sets at least min_test_images and one metric gate,
    every evaluation ends with gate_decision='policy_not_configured'.
    """
    __tablename__ = "evaluation_policies"

    id = Column(Integer, primary_key=True, default=1)
    min_test_images = Column(Integer, nullable=True)
    min_objects_per_class = Column(Integer, nullable=True)
    require_class_coverage = Column(Boolean, nullable=False, default=True)
    min_map50 = Column(Float, nullable=True)
    min_map50_95 = Column(Float, nullable=True)
    min_precision = Column(Float, nullable=True)
    min_recall = Column(Float, nullable=True)
    min_class_recall = Column(Float, nullable=True)
    max_map50_regression = Column(Float, nullable=True)
    updated_by = Column(String(36), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ModelApproval(Base):
    """
    Immutable human review decision on one A3 evaluation of a candidate (Block A4).

    decision : approved | rejected. UNIQUE(evaluation_id) = exactly one final
    decision per evaluation; re-review requires a new evaluation. The evidence
    columns pin what the administrator saw; activation re-verifies all of them.
    """
    __tablename__ = "model_approvals"

    approval_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    model_id = Column(String(36), ForeignKey("model_versions.model_id"), nullable=False, index=True)
    model_version = Column(String(20), nullable=False)
    job_id = Column(String(36), ForeignKey("training_jobs.job_id"), nullable=False)
    snapshot_id = Column(Integer, ForeignKey("training_snapshots.snapshot_id"), nullable=False)
    evaluation_id = Column(String(36), ForeignKey("model_evaluations.evaluation_id"), nullable=False, unique=True)
    evaluation_config_hash = Column(String(64), nullable=False)
    evaluation_status = Column(String(20), nullable=False)
    gate_decision = Column(String(32), nullable=True)
    weights_sha256 = Column(String(64), nullable=False)
    class_map_sha256 = Column(String(64), nullable=False)
    manifest_sha256 = Column(String(64), nullable=True)
    decision = Column(String(16), nullable=False)
    reason = Column(Text, nullable=True)
    decided_by = Column(String(36), nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ModelDeployment(Base):
    """
    Durable activation / rollback state machine (Block A4).

    kind   : activation | rollback | legacy_activation
    status : pending -> activating -> active -> superseded | rolled_back
                        pending|activating -> failed
    inflight = 'global' while pending/activating (UNIQUE): at most one deployment
    runs at a time. model ids are plain strings (no FK) so history outlives rows.
    """
    __tablename__ = "model_deployments"

    deployment_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    model_id = Column(String(36), nullable=False, index=True)
    model_version = Column(String(20), nullable=True)
    approval_id = Column(String(36), nullable=True)
    evaluation_id = Column(String(36), nullable=True)
    snapshot_id = Column(Integer, nullable=True)
    weights_sha256 = Column(String(64), nullable=False)
    artifact_file = Column(String(255), nullable=True)
    previous_model_id = Column(String(36), nullable=True)
    previous_sha256 = Column(String(64), nullable=True)
    previous_artifact_file = Column(String(255), nullable=True)
    serving_switched = Column(Boolean, nullable=False, default=False)
    reason = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    requested_by = Column(String(36), nullable=True)
    requested_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
                          index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    replaced_by = Column(String(36), nullable=True)
    lease_token = Column(String(36), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    inflight = Column(String(16), nullable=True, unique=True)


class DeploymentEvent(Base):
    """Append-only audit log for approval, activation and rollback (Block A4)."""
    __tablename__ = "deployment_events"

    event_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = Column(String(40), nullable=False, index=True)
    model_id = Column(String(36), nullable=True, index=True)
    deployment_id = Column(String(36), nullable=True, index=True)
    approval_id = Column(String(36), nullable=True)
    actor_id = Column(String(36), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
                        index=True)


class TrainingJobEvent(Base):
    """
    Append-only training attempt history (Block A5). One row per status change or
    dispatch attempt of a TrainingJob, written automatically in the same
    transaction as the change (see _record_job_event). job_id has no FK so the
    history outlives job rows.
    """
    __tablename__ = "training_job_events"

    event_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), nullable=False, index=True)
    event_type = Column(String(32), nullable=False)
    status_before = Column(String(20), nullable=True)
    status_after = Column(String(20), nullable=True)
    attempt = Column(Integer, nullable=True)
    dispatch_attempts = Column(Integer, nullable=True)
    worker_id = Column(String(128), nullable=True)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
                        index=True)


class SchedulerHeartbeat(Base):
    """Persisted last-run state of each background scheduler job (Block A5)."""
    __tablename__ = "scheduler_heartbeats"

    job_name = Column(String(64), primary_key=True)
    interval_seconds = Column(Integer, nullable=False)
    process_id = Column(String(128), nullable=True)
    last_started_at = Column(DateTime(timezone=True), nullable=True)
    last_finished_at = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String(16), nullable=True)          # running | ok | error
    last_error = Column(Text, nullable=True)
    last_duration_seconds = Column(Float, nullable=True)
    run_count = Column(Integer, nullable=False, default=0)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class DeploymentRecordImmutableError(Exception):
    pass


@event.listens_for(ModelApproval, "before_update")
@event.listens_for(DeploymentEvent, "before_update")
@event.listens_for(TrainingJobEvent, "before_update")
def _guard_append_only_update(mapper, connection, target):
    raise DeploymentRecordImmutableError(f"{type(target).__name__} rows are immutable")


@event.listens_for(ModelApproval, "before_delete")
@event.listens_for(DeploymentEvent, "before_delete")
@event.listens_for(TrainingJobEvent, "before_delete")
def _guard_append_only_delete(mapper, connection, target):
    raise DeploymentRecordImmutableError(f"{type(target).__name__} rows cannot be deleted")


def _job_event_type(before, after, attempt, dispatch_changed, dispatched_now) -> str:
    if before is None:
        return "created"
    if before != after:
        if after == "running":
            return "claimed"
        if after == "queued":
            return "requeued"
        if after == "completed":
            return "completed"
        if after == "failed":
            from app.config import settings
            return "retries_exhausted" if (attempt or 0) >= settings.TRAINING_MAX_ATTEMPTS else "failed"
        return "status_changed"
    if dispatch_changed:
        return "dispatched" if dispatched_now else "dispatch_failed"
    return "updated"


def _record_job_event(connection, target, inserted: bool) -> None:
    from sqlalchemy import inspect as sa_inspect
    state = sa_inspect(target)
    status_hist = state.attrs.status.history
    dispatch_hist = state.attrs.dispatch_attempts.history
    if inserted:
        before, after = None, target.status
    elif status_hist.has_changes() or dispatch_hist.has_changes():
        after = target.status
        if status_hist.deleted:
            before = status_hist.deleted[0]
        else:
            # Expired attribute (object reused after a commit): before_update read the
            # row's stored status just before the UPDATE ran.
            before = target.__dict__.get("_zwm_prev_status")
        if before == after and not dispatch_hist.has_changes():
            return
    else:
        return
    dispatched_now = state.attrs.dispatched_at.history.has_changes() and target.dispatched_at is not None
    kind = _job_event_type(before, after, target.attempt_count, dispatch_hist.has_changes(), dispatched_now)
    connection.execute(TrainingJobEvent.__table__.insert().values(
        event_id=str(uuid.uuid4()), job_id=target.job_id, event_type=kind,
        status_before=before, status_after=after, attempt=target.attempt_count,
        dispatch_attempts=target.dispatch_attempts, worker_id=target.worker_id,
        message=(target.error_message or None)
        if kind in ("requeued", "failed", "retries_exhausted", "dispatch_failed") else None,
        created_at=datetime.now(timezone.utc),
    ))


@event.listens_for(TrainingJob, "after_insert")
def _job_inserted(mapper, connection, target):
    _record_job_event(connection, target, inserted=True)


@event.listens_for(TrainingJob, "before_update")
def _job_before_update(mapper, connection, target):
    from sqlalchemy import inspect as sa_inspect, select
    if not sa_inspect(target).attrs.status.history.deleted:
        target.__dict__["_zwm_prev_status"] = connection.execute(
            select(TrainingJob.__table__.c.status).where(TrainingJob.__table__.c.job_id == target.job_id)
        ).scalar()


@event.listens_for(TrainingJob, "after_update")
def _job_updated(mapper, connection, target):
    _record_job_event(connection, target, inserted=False)


class ActivationGuardError(Exception):
    pass


# Session.info key set only by the A4 deployment service while it switches models.
CURRENT_MODEL_CHANGE_KEY = "zwm_a4_current_model_change"


def _register_activation_guard():
    """
    Backstop: no ORM flush may mark a snapshot-trained candidate current unless the
    A4 deployment service authorised it. Legacy (non-snapshot) models are unaffected.
    """
    from sqlalchemy import select
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy.orm import Session as _Session

    @event.listens_for(_Session, "before_flush")
    def _guard_current_model(session, flush_context, instances):
        if session.info.get(CURRENT_MODEL_CHANGE_KEY):
            return
        for obj in list(session.new) + list(session.dirty):
            if not isinstance(obj, ModelVersion) or obj.is_current is not True:
                continue
            if obj not in session.new and not sa_inspect(obj).attrs.is_current.history.has_changes():
                continue
            snapshot_id = session.connection().execute(
                select(TrainingJob.snapshot_id).where(TrainingJob.job_id == obj.job_id)
            ).scalar()
            if snapshot_id is not None:
                raise ActivationGuardError(
                    "snapshot-trained candidates can only be activated through the approval workflow"
                )

    @event.listens_for(_Session, "do_orm_execute")
    def _guard_bulk_current(orm_execute_state):
        """Bulk ORM UPDATEs may clear is_current but never set it outside the deployment engine."""
        if not orm_execute_state.is_update or orm_execute_state.session.info.get(CURRENT_MODEL_CHANGE_KEY):
            return
        stmt = orm_execute_state.statement
        if getattr(stmt, "table", None) is None or stmt.table.name != ModelVersion.__tablename__:
            return
        for col, value in (getattr(stmt, "_values", None) or {}).items():
            name = getattr(col, "key", None) or getattr(col, "name", None) or str(col)
            if name == "is_current" and getattr(value, "value", value) is not False:
                raise ActivationGuardError(
                    "bulk updates may not mark a model current; use the deployment workflow"
                )


_register_activation_guard()


# PostgreSQL backstop for the activation boundary (Block A4.1): a snapshot-trained
# candidate can only become current inside a transaction where the A4 deployment
# service ran set_config('zwm.allow_current_change', 'on', true). Shared with the
# Alembic migration so create_all() test databases get the same protection.
ACTIVATION_GUARD_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION zwm_guard_snapshot_activation() RETURNS trigger AS $$
BEGIN
    IF NEW.is_current IS TRUE
       AND (TG_OP = 'INSERT' OR OLD.is_current IS DISTINCT FROM TRUE)
       AND EXISTS (SELECT 1 FROM training_jobs j WHERE j.job_id = NEW.job_id AND j.snapshot_id IS NOT NULL)
       AND coalesce(current_setting('zwm.allow_current_change', true), '') <> 'on' THEN
        RAISE EXCEPTION 'snapshot-trained candidates can only be activated through the approval workflow'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql
"""
ACTIVATION_GUARD_TRIGGER_SQL = (
    "CREATE TRIGGER trg_model_versions_activation_guard "
    "BEFORE INSERT OR UPDATE OF is_current ON model_versions "
    "FOR EACH ROW EXECUTE FUNCTION zwm_guard_snapshot_activation()"
)

event.listen(ModelVersion.__table__, "after_create",
             DDL(ACTIVATION_GUARD_FUNCTION_SQL).execute_if(dialect="postgresql"))
event.listen(ModelVersion.__table__, "after_create",
             DDL(ACTIVATION_GUARD_TRIGGER_SQL).execute_if(dialect="postgresql"))


class TrainingSnapshot(Base):
    """
    Locked cumulative dataset milestone (V1 = threshold, V2 = V1 + threshold, ...).

    Membership (TrainingSnapshotImage rows) and the milestone fields are immutable
    once created. Only ``status`` may change later (training lifecycle, Block A2).
    """
    __tablename__ = "training_snapshots"

    snapshot_id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(Integer, nullable=False, unique=True)
    threshold = Column(Integer, nullable=False)
    milestone_count = Column(Integer, nullable=False, unique=True)
    dataset_size = Column(Integer, nullable=False)
    first_sequence = Column(BigInteger, nullable=True)
    last_sequence = Column(BigInteger, nullable=True)
    # Frozen YOLO class mapping: [{yolo_index, category_id, class_code, class_name, is_active}]
    class_map = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="locked")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    images = relationship(
        "TrainingSnapshotImage",
        backref="snapshot",
        lazy=True,
        order_by="TrainingSnapshotImage.position",
    )


class TrainingSnapshotImage(Base):
    """
    Exact image membership of a snapshot.

    image_id intentionally has no FK: a snapshot is a historical record and must
    not block (or be mutated by) later image/user deletion.
    """
    __tablename__ = "training_snapshot_images"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "position", name="uq_training_snapshot_images_position"),
    )

    snapshot_id = Column(Integer, ForeignKey("training_snapshots.snapshot_id"), primary_key=True)
    image_id = Column(String(36), primary_key=True, index=True)
    position = Column(Integer, nullable=False)
    training_sequence = Column(BigInteger, nullable=False)
    # train | val | test — frozen when the snapshot is locked (Block A2)
    split_type = Column(String(10), nullable=True)


_SNAPSHOT_IMMUTABLE_FIELDS = (
    "version", "threshold", "milestone_count", "dataset_size",
    "first_sequence", "last_sequence", "class_map",
)


class SnapshotImmutableError(Exception):
    pass


@event.listens_for(TrainingSnapshot, "before_update")
def _guard_snapshot_update(mapper, connection, target):
    from sqlalchemy import inspect as sa_inspect
    state = sa_inspect(target)
    for field in _SNAPSHOT_IMMUTABLE_FIELDS:
        if state.attrs[field].history.has_changes():
            raise SnapshotImmutableError(f"TrainingSnapshot.{field} is immutable")


@event.listens_for(TrainingSnapshotImage, "before_update")
def _guard_snapshot_image_update(mapper, connection, target):
    from sqlalchemy import inspect as sa_inspect
    state = sa_inspect(target)
    for field in ("snapshot_id", "image_id", "position", "training_sequence", "split_type"):
        if state.attrs[field].history.has_changes():
            raise SnapshotImmutableError(f"TrainingSnapshotImage.{field} is immutable")


@event.listens_for(TrainingSnapshotImage, "before_delete")
def _guard_snapshot_image_delete(mapper, connection, target):
    raise SnapshotImmutableError("TrainingSnapshotImage rows cannot be deleted")


# ---------------------------------------------------------------------------
# Dataset integrity guards (backstop for any ORM delete path)
# ---------------------------------------------------------------------------

class TrainingDataProtectedError(Exception):
    pass


def _register_integrity_guards():
    from sqlalchemy import select, exists
    from app.models.image import Image
    from app.models.category import Category

    @event.listens_for(Image, "before_delete")
    def _guard_snapshot_image_hard_delete(mapper, connection, target):
        in_snapshot = connection.execute(
            select(exists().where(TrainingSnapshotImage.image_id == target.image_id))
        ).scalar()
        if in_snapshot:
            raise TrainingDataProtectedError(
                f"Image {target.image_id} belongs to a locked training snapshot and cannot be deleted"
            )

    @event.listens_for(Category, "before_delete")
    def _guard_indexed_category_hard_delete(mapper, connection, target):
        if target.yolo_class_index is not None:
            raise TrainingDataProtectedError(
                f"Category {target.category_id} owns YOLO class index {target.yolo_class_index}; "
                "archive it (is_active=False) instead of deleting"
            )

    from app.models.annotation import Annotation
    from sqlalchemy import inspect as sa_inspect

    def _image_is_training_eligible(connection, image_id) -> bool:
        return connection.execute(
            select(Image.training_sequence).where(Image.image_id == image_id)
        ).scalar() is not None

    @event.listens_for(Annotation, "before_delete")
    def _guard_eligible_annotation_delete(mapper, connection, target):
        if _image_is_training_eligible(connection, target.image_id):
            raise TrainingDataProtectedError(
                f"Annotation {target.annotation_id} belongs to a training-eligible image and cannot be deleted"
            )

    _protected_annotation_fields = (
        "image_id", "category_id", "annotation_type", "label_data_json", "image_width", "image_height",
        "ai_generated",                                   # A6.0: provenance evidence
    )

    @event.listens_for(Annotation, "before_update")
    def _guard_eligible_annotation_update(mapper, connection, target):
        state = sa_inspect(target)
        if any(state.attrs[f].history.has_changes() for f in _protected_annotation_fields):
            if _image_is_training_eligible(connection, target.image_id):
                raise TrainingDataProtectedError(
                    f"Annotation {target.annotation_id} belongs to a training-eligible image and cannot be modified"
                )


_register_integrity_guards()
