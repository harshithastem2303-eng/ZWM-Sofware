"""
Prediction feedback (ZWM v1.1.0, Block A6.2).

A PredictionFeedback is one user's report that an A6.1 prediction was wrong, with an
optional suggested correction. A FeedbackDecision is one administrator's decision
about it. Neither ever touches the prediction, annotations, label files or training
eligibility: "approved" only means accepted for a later, governed correction workflow.

Lifecycle: pending -> approved | rejected (terminal, exactly one decision).
  * feedback rows are immutable except that single status transition, which must be
    backed by the decision row of the same outcome inserted in the same transaction;
  * decision rows are append-only, at most one per feedback (unique), and the reviewer
    may never be the submitter, by id or e-mail (independent review);
  * neither table allows DELETE.
The ORM enforces this for application code; PostgreSQL triggers enforce it whatever
the code path (shared with the Alembic migration so create_all() test databases get
the same protection).

prediction_id is a real foreign key: prediction records are append-only, so the
reference can never dangle. Copies of the model reference and the targeted detection
are kept on the feedback row as audit evidence of what the user was looking at.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DDL, DateTime, ForeignKey, Index, Integer, String, Text, event, inspect, text

from app.database import Base

FEEDBACK_INCORRECT_CLASS = "incorrect_class"
FEEDBACK_INCORRECT_GEOMETRY = "incorrect_geometry"      # bounding box or polygon
FEEDBACK_MISSED_OBJECT = "missed_object"
FEEDBACK_FALSE_DETECTION = "false_detection"
FEEDBACK_OTHER = "other"
FEEDBACK_TYPES = (FEEDBACK_INCORRECT_CLASS, FEEDBACK_INCORRECT_GEOMETRY, FEEDBACK_MISSED_OBJECT,
                  FEEDBACK_FALSE_DETECTION, FEEDBACK_OTHER)

STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED = "pending", "approved", "rejected"
DECISIONS = (STATUS_APPROVED, STATUS_REJECTED)

TARGET_PREDICTION = "prediction"          # feedback about the prediction as a whole


def detection_target(index: int) -> str:
    return f"detection:{index}"


class FeedbackImmutableError(Exception):
    pass


class PredictionFeedback(Base):
    __tablename__ = "prediction_feedback"
    __table_args__ = (
        Index("ix_prediction_feedback_status_submitted", "status", "submitted_at"),
        Index("ix_prediction_feedback_submitter_submitted", "submitted_by", "submitted_at"),
        # Duplicate rule: one open (pending) or accepted (approved) report per user,
        # prediction, feedback type and target. A rejected report may be resubmitted.
        Index("uq_prediction_feedback_open", "prediction_id", "submitted_by", "feedback_type", "target",
              unique=True, postgresql_where=text("status IN ('pending', 'approved')"),
              sqlite_where=text("status IN ('pending', 'approved')")),
    )

    feedback_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    prediction_id = Column(String(36), ForeignKey("prediction_records.prediction_id", ondelete="RESTRICT"),
                           nullable=False, index=True)
    submitted_by = Column(String(36), nullable=False)
    submitter_role = Column(String(20), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    environment = Column(String(32), nullable=False)

    feedback_type = Column(String(32), nullable=False)
    target = Column(String(24), nullable=False)                     # 'prediction' | 'detection:<index>'
    detection_index = Column(Integer, nullable=True)
    explanation = Column(Text, nullable=True)
    suggested_category_id = Column(Integer, nullable=True)          # no FK: evidence outlives categories
    suggested_class_name = Column(String(50), nullable=True)        # as it was at submission
    suggested_yolo_class_index = Column(Integer, nullable=True)
    suggested_geometry = Column(JSON, nullable=True)                # {"type": "bbox"|"polygon", ...}

    # audit copies of the original prediction / model reference (never re-derived)
    image_id = Column(String(36), nullable=True, index=True)
    prediction_source = Column(String(32), nullable=False)
    model_kind = Column(String(32), nullable=False)
    model_attribution = Column(String(32), nullable=False)
    model_sha256 = Column(String(64), nullable=True)
    model_version_id = Column(String(36), nullable=True)
    deployment_id = Column(String(36), nullable=True)
    original_detection = Column(JSON, nullable=True)                # the targeted detection, verbatim

    status = Column(String(16), nullable=False, default=STATUS_PENDING)


class FeedbackDecision(Base):
    __tablename__ = "prediction_feedback_decisions"

    decision_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    feedback_id = Column(String(36), ForeignKey("prediction_feedback.feedback_id", ondelete="RESTRICT"),
                         nullable=False, unique=True)
    decision = Column(String(16), nullable=False)                  # approved | rejected
    reviewer_id = Column(String(36), nullable=False)
    reviewer_email = Column(String(255), nullable=True)
    reason = Column(Text, nullable=True)
    previous_status = Column(String(16), nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


@event.listens_for(PredictionFeedback, "before_update")
def _feedback_only_status_transition(mapper, connection, target):
    state = inspect(target)
    changed = {a.key for a in state.attrs if a.history.has_changes()}
    if changed - {"status"}:
        raise FeedbackImmutableError("prediction feedback is immutable")
    hist = state.attrs.status.history
    old = hist.deleted[0] if hist.deleted else None
    if old != STATUS_PENDING or target.status not in DECISIONS:
        raise FeedbackImmutableError("feedback status can only move from pending to approved or rejected")


@event.listens_for(PredictionFeedback, "before_delete")
def _feedback_no_delete(mapper, connection, target):
    raise FeedbackImmutableError("prediction feedback cannot be deleted")


@event.listens_for(FeedbackDecision, "before_update")
def _decision_no_update(mapper, connection, target):
    raise FeedbackImmutableError("feedback decisions are immutable")


@event.listens_for(FeedbackDecision, "before_delete")
def _decision_no_delete(mapper, connection, target):
    raise FeedbackImmutableError("feedback decisions cannot be deleted")


FEEDBACK_GUARD_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION zwm_guard_prediction_feedback() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'prediction feedback cannot be deleted' USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.status IS DISTINCT FROM 'pending' THEN
            RAISE EXCEPTION 'prediction feedback must be submitted as pending' USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    IF (to_jsonb(NEW) - 'status') IS DISTINCT FROM (to_jsonb(OLD) - 'status') THEN
        RAISE EXCEPTION 'prediction feedback is immutable' USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.status <> 'pending' OR NEW.status NOT IN ('approved', 'rejected') THEN
        RAISE EXCEPTION 'feedback status can only move from pending to approved or rejected'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM prediction_feedback_decisions d
                   WHERE d.feedback_id = NEW.feedback_id AND d.decision = NEW.status) THEN
        RAISE EXCEPTION 'a feedback status change requires a recorded decision' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql
"""
FEEDBACK_GUARD_TRIGGER_SQL = (
    "CREATE TRIGGER trg_prediction_feedback_guard BEFORE INSERT OR UPDATE OR DELETE ON prediction_feedback "
    "FOR EACH ROW EXECUTE FUNCTION zwm_guard_prediction_feedback()"
)

DECISION_GUARD_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION zwm_guard_feedback_decisions() RETURNS trigger AS $$
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        RAISE EXCEPTION 'feedback decisions are append-only' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.decision NOT IN ('approved', 'rejected') THEN
        RAISE EXCEPTION 'invalid feedback decision' USING ERRCODE = 'check_violation';
    END IF;
    -- FOR UPDATE serialises concurrent decisions on the same feedback: a waiting
    -- transaction re-reads the row after the first commits and sees it decided.
    PERFORM 1 FROM prediction_feedback f WHERE f.feedback_id = NEW.feedback_id
        AND f.status = 'pending' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'feedback has already been decided' USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM prediction_feedback f
               LEFT JOIN users u ON u.user_id = f.submitted_by
               WHERE f.feedback_id = NEW.feedback_id
                 AND (f.submitted_by = NEW.reviewer_id
                      OR (NEW.reviewer_email IS NOT NULL
                          AND lower(u.email) = lower(NEW.reviewer_email)))) THEN
        RAISE EXCEPTION 'feedback decisions require an independent reviewer' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql
"""
DECISION_GUARD_TRIGGER_SQL = (
    "CREATE TRIGGER trg_feedback_decisions_guard BEFORE INSERT OR UPDATE OR DELETE "
    "ON prediction_feedback_decisions FOR EACH ROW EXECUTE FUNCTION zwm_guard_feedback_decisions()"
)

# plpgsql resolves the other table only at run time, so creation order does not matter.
event.listen(PredictionFeedback.__table__, "after_create",
             DDL(FEEDBACK_GUARD_FUNCTION_SQL).execute_if(dialect="postgresql"))
event.listen(PredictionFeedback.__table__, "after_create",
             DDL(FEEDBACK_GUARD_TRIGGER_SQL).execute_if(dialect="postgresql"))
event.listen(FeedbackDecision.__table__, "after_create",
             DDL(DECISION_GUARD_FUNCTION_SQL).execute_if(dialect="postgresql"))
event.listen(FeedbackDecision.__table__, "after_create",
             DDL(DECISION_GUARD_TRIGGER_SQL).execute_if(dialect="postgresql"))
