"""
Immutable label revisions (ZWM v1.1.0, Block A6.3).

A LabelRevision is one complete, reproducible label state of an image: every object
(geometry, class reference, author, AI flag) plus the class map it was resolved
against and canonical hashes. Revisions are never updated or deleted; a change is a
new revision whose parent is the revision it was derived from.

Sources:
  * human_annotation  -- a recorded capture of the image's current annotation rows
                         (status "recorded"; A6.0 alone governs its eligibility);
  * approved_feedback -- a proposal built from one A6.2 feedback with an approved
                         decision (at most one revision per feedback);
  * admin_correction  -- a proposal by an administrator (restore of an earlier state).

Lifecycle (proposals): draft -> submitted -> approved | rejected, then an approved
revision may be activated once. The status is never stored: it is derived from the
append-only LabelRevisionEvent rows (unique per revision and event). The only mutable
row is the per-image pointer LabelRevisionHead, kept in its own table and only ever
moved to a recorded capture or an activated revision of the same image.

Activation never touches a training-eligible or snapshotted image (its labels are
frozen); it rewrites the mutable annotation rows to the revision and re-finalizes the
label, after which the existing A6.0 review decides training eligibility.

PostgreSQL triggers back the ORM guards whatever the code path (shared with the
Alembic migration so create_all() test databases get the same protection).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DDL, DateTime, ForeignKey, Index, Integer, String, Text, event, text

from app.database import Base

SOURCE_HUMAN, SOURCE_FEEDBACK, SOURCE_ADMIN = "human_annotation", "approved_feedback", "admin_correction"
SOURCES = (SOURCE_HUMAN, SOURCE_FEEDBACK, SOURCE_ADMIN)

EVENT_CREATED, EVENT_SUBMITTED = "created", "submitted"
EVENT_APPROVED, EVENT_REJECTED, EVENT_ACTIVATED = "approved", "rejected", "activated"
EVENTS = (EVENT_CREATED, EVENT_SUBMITTED, EVENT_APPROVED, EVENT_REJECTED, EVENT_ACTIVATED)

STATUS_RECORDED, STATUS_DRAFT, STATUS_SUBMITTED = "recorded", "draft", "submitted"
STATUS_APPROVED, STATUS_REJECTED = "approved", "rejected"


class LabelRevisionImmutableError(Exception):
    pass


class LabelRevision(Base):
    __tablename__ = "label_revisions"
    __table_args__ = (
        Index("uq_label_revisions_image_number", "image_id", "revision_number", unique=True),
        # an approved feedback is applied at most once
        Index("uq_label_revisions_feedback", "feedback_id", unique=True,
              postgresql_where=text("feedback_id IS NOT NULL"), sqlite_where=text("feedback_id IS NOT NULL")),
    )

    revision_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    image_id = Column(String(36), nullable=False, index=True)          # no FK: evidence outlives image rows
    revision_number = Column(Integer, nullable=False)
    parent_revision_id = Column(String(36), ForeignKey("label_revisions.revision_id", ondelete="RESTRICT"),
                                nullable=True)
    source = Column(String(24), nullable=False)
    feedback_id = Column(String(36), ForeignKey("prediction_feedback.feedback_id", ondelete="RESTRICT"),
                         nullable=True)
    feedback_decision_id = Column(String(36), ForeignKey("prediction_feedback_decisions.decision_id",
                                                         ondelete="RESTRICT"), nullable=True)
    prediction_id = Column(String(36), ForeignKey("prediction_records.prediction_id", ondelete="RESTRICT"),
                           nullable=True)
    created_by = Column(String(36), nullable=False)
    created_by_email = Column(String(255), nullable=True)
    created_by_role = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    reason = Column(Text, nullable=True)

    # complete label state: {"image": {"width", "height"}, "objects": [...]} (see label_revision_service)
    contents = Column(JSON, nullable=False)
    object_count = Column(Integer, nullable=False)
    correction = Column(JSON, nullable=True)                 # what was applied to the parent, verbatim
    class_map = Column(JSON, nullable=False)                 # YOLO class map the objects were resolved against
    class_map_sha256 = Column(String(64), nullable=False)
    content_sha256 = Column(String(64), nullable=False)      # canonical contents
    annotation_fingerprint = Column(String(64), nullable=False)   # A6.0 fingerprint the rows have in this state
    label_text = Column(Text, nullable=False)                # canonical YOLO label derived from the contents
    label_sha256 = Column(String(64), nullable=False)

    # review / eligibility references of the image when the revision was created
    base_label_sha256 = Column(String(64), nullable=True)         # images.label_sha256 (finalized revision)
    base_training_sequence = Column(Integer, nullable=True)
    base_training_review_id = Column(String(36), nullable=True)
    base_label_provenance = Column(String(20), nullable=True)
    installed_label_sha256 = Column(String(64), nullable=True)    # recorded captures: the label file on disk
    installed_label_text = Column(Text, nullable=True)


class LabelRevisionEvent(Base):
    __tablename__ = "label_revision_events"
    __table_args__ = (
        Index("uq_label_revision_events_once", "revision_id", "event", unique=True),
        # exactly one decision per revision
        Index("uq_label_revision_events_decision", "revision_id", unique=True,
              postgresql_where=text("event IN ('approved', 'rejected')"),
              sqlite_where=text("event IN ('approved', 'rejected')")),
        Index("ix_label_revision_events_image", "image_id", "created_at"),
    )

    event_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    revision_id = Column(String(36), ForeignKey("label_revisions.revision_id", ondelete="RESTRICT"),
                         nullable=False)
    image_id = Column(String(36), nullable=False)
    event = Column(String(16), nullable=False)
    from_status = Column(String(16), nullable=True)
    to_status = Column(String(16), nullable=False)
    actor_id = Column(String(36), nullable=False)
    actor_email = Column(String(255), nullable=True)
    actor_role = Column(String(20), nullable=False)
    reason = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class LabelRevisionHead(Base):
    """Mutable pointer: the image's current revision (separate from immutable evidence)."""
    __tablename__ = "label_revision_heads"

    image_id = Column(String(36), primary_key=True)
    revision_id = Column(String(36), ForeignKey("label_revisions.revision_id", ondelete="RESTRICT"),
                         nullable=False)
    event_id = Column(String(36), ForeignKey("label_revision_events.event_id", ondelete="RESTRICT"),
                      nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


@event.listens_for(LabelRevision, "before_update")
def _revision_no_update(mapper, connection, target):
    raise LabelRevisionImmutableError("label revisions are immutable")


@event.listens_for(LabelRevision, "before_delete")
def _revision_no_delete(mapper, connection, target):
    raise LabelRevisionImmutableError("label revisions cannot be deleted")


@event.listens_for(LabelRevisionEvent, "before_update")
def _event_no_update(mapper, connection, target):
    raise LabelRevisionImmutableError("label revision events are immutable")


@event.listens_for(LabelRevisionEvent, "before_delete")
def _event_no_delete(mapper, connection, target):
    raise LabelRevisionImmutableError("label revision events cannot be deleted")


@event.listens_for(LabelRevisionHead, "before_delete")
def _head_no_delete(mapper, connection, target):
    raise LabelRevisionImmutableError("label revision heads cannot be deleted")


REVISION_GUARD_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION zwm_guard_label_revisions() RETURNS trigger AS $$
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        RAISE EXCEPTION 'label revisions are append-only' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.source NOT IN ('human_annotation', 'approved_feedback', 'admin_correction') THEN
        RAISE EXCEPTION 'invalid label revision source' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.parent_revision_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM label_revisions p
            WHERE p.revision_id = NEW.parent_revision_id AND p.image_id = NEW.image_id) THEN
        RAISE EXCEPTION 'a parent revision must belong to the same image' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.source = 'approved_feedback' AND NOT EXISTS (
            SELECT 1 FROM prediction_feedback f
            JOIN prediction_feedback_decisions d ON d.feedback_id = f.feedback_id
            JOIN prediction_records p ON p.prediction_id = f.prediction_id
            WHERE f.feedback_id = NEW.feedback_id
              AND d.decision_id = NEW.feedback_decision_id
              AND f.status = 'approved' AND d.decision = 'approved'
              AND f.prediction_id = NEW.prediction_id
              AND f.image_id = NEW.image_id AND p.image_id = NEW.image_id) THEN
        RAISE EXCEPTION 'a feedback revision requires approved feedback for the same image and prediction'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.source <> 'approved_feedback' AND NEW.feedback_id IS NOT NULL THEN
        RAISE EXCEPTION 'only feedback revisions reference feedback' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql
"""
REVISION_GUARD_TRIGGER_SQL = (
    "CREATE TRIGGER trg_label_revisions_guard BEFORE INSERT OR UPDATE OR DELETE ON label_revisions "
    "FOR EACH ROW EXECUTE FUNCTION zwm_guard_label_revisions()"
)

EVENT_GUARD_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION zwm_guard_label_revision_events() RETURNS trigger AS $$
DECLARE
    r_image varchar;
    r_source varchar;
    r_created_by varchar;
    r_created_email varchar;
    r_feedback varchar;
    seen text[];
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        RAISE EXCEPTION 'label revision events are append-only' USING ERRCODE = 'check_violation';
    END IF;
    -- FOR UPDATE serialises concurrent transitions of one revision: a waiting
    -- transaction re-reads the events after the first commits.
    SELECT image_id, source, created_by, created_by_email, feedback_id
        INTO r_image, r_source, r_created_by, r_created_email, r_feedback
        FROM label_revisions WHERE revision_id = NEW.revision_id FOR UPDATE;
    IF NOT FOUND OR r_image <> NEW.image_id THEN
        RAISE EXCEPTION 'label revision event for an unknown revision' USING ERRCODE = 'check_violation';
    END IF;
    SELECT coalesce(array_agg(e.event), '{}') INTO seen FROM label_revision_events e
        WHERE e.revision_id = NEW.revision_id;
    IF NEW.event = 'created' THEN
        IF cardinality(seen) > 0 THEN
            RAISE EXCEPTION 'label revision already created' USING ERRCODE = 'check_violation';
        END IF;
    ELSIF NEW.event = 'submitted' THEN
        IF r_source = 'human_annotation' OR NOT ('created' = ANY(seen)) OR 'submitted' = ANY(seen) THEN
            RAISE EXCEPTION 'only a draft revision can be submitted' USING ERRCODE = 'check_violation';
        END IF;
    ELSIF NEW.event IN ('approved', 'rejected') THEN
        IF NOT ('submitted' = ANY(seen)) OR 'approved' = ANY(seen) OR 'rejected' = ANY(seen) THEN
            RAISE EXCEPTION 'only a submitted, undecided revision can be decided' USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.actor_id = r_created_by
           OR (NEW.actor_email IS NOT NULL AND lower(NEW.actor_email) = lower(r_created_email))
           OR EXISTS (SELECT 1 FROM prediction_feedback f LEFT JOIN users u ON u.user_id = f.submitted_by
                      WHERE f.feedback_id = r_feedback
                        AND (f.submitted_by = NEW.actor_id
                             OR (NEW.actor_email IS NOT NULL AND lower(u.email) = lower(NEW.actor_email)))) THEN
            RAISE EXCEPTION 'label revision decisions require an independent reviewer'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF NEW.event = 'activated' THEN
        IF NOT ('approved' = ANY(seen)) OR 'rejected' = ANY(seen) OR 'activated' = ANY(seen) THEN
            RAISE EXCEPTION 'only an approved revision can be activated' USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        RAISE EXCEPTION 'invalid label revision event' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql
"""
EVENT_GUARD_TRIGGER_SQL = (
    "CREATE TRIGGER trg_label_revision_events_guard BEFORE INSERT OR UPDATE OR DELETE "
    "ON label_revision_events FOR EACH ROW EXECUTE FUNCTION zwm_guard_label_revision_events()"
)

HEAD_GUARD_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION zwm_guard_label_revision_heads() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'label revision heads cannot be deleted' USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.image_id <> OLD.image_id THEN
        RAISE EXCEPTION 'a label revision head cannot move to another image' USING ERRCODE = 'check_violation';
    END IF;
    IF NOT EXISTS (
            SELECT 1 FROM label_revision_events e JOIN label_revisions r ON r.revision_id = e.revision_id
            WHERE e.event_id = NEW.event_id AND e.revision_id = NEW.revision_id AND r.image_id = NEW.image_id
              AND ((e.event = 'created' AND r.source = 'human_annotation') OR e.event = 'activated')) THEN
        RAISE EXCEPTION 'the current label revision must be a recorded or activated revision of the image'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql
"""
HEAD_GUARD_TRIGGER_SQL = (
    "CREATE TRIGGER trg_label_revision_heads_guard BEFORE INSERT OR UPDATE OR DELETE "
    "ON label_revision_heads FOR EACH ROW EXECUTE FUNCTION zwm_guard_label_revision_heads()"
)

# plpgsql resolves the other tables only at run time, so creation order does not matter.
for _table, _sqls in ((LabelRevision.__table__, (REVISION_GUARD_FUNCTION_SQL, REVISION_GUARD_TRIGGER_SQL)),
                      (LabelRevisionEvent.__table__, (EVENT_GUARD_FUNCTION_SQL, EVENT_GUARD_TRIGGER_SQL)),
                      (LabelRevisionHead.__table__, (HEAD_GUARD_FUNCTION_SQL, HEAD_GUARD_TRIGGER_SQL))):
    for _sql in _sqls:
        event.listen(_table, "after_create", DDL(_sql).execute_if(dialect="postgresql"))
