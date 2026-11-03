"""
Human label review evidence (ZWM v1.1.0, Block A6.0).

A LabelReview records one administrator decision about ONE exact label revision of
an image: the SHA-256 of the installed YOLO label file plus a fingerprint of the
annotation set it was generated from. Rows are append-only.

Training eligibility (training_dataset_service.mark_training_eligible) comes from
exactly one of two kinds of evidence:
  * user_confirmed -- a human-only revision (no AI-generated annotation, no AI
    suggestions served for the image, every annotation by the owner or finalizer,
    never rejected) finalized by a person: A1's user-owned finalization;
  * admin_approved -- an ``approved`` review whose hashes match the current label.
    Required whenever AI was involved or someone else annotated the image.

PostgreSQL backstops (shared with the Alembic migrations so create_all() test
databases get the same protection):
  * label_reviews rows can never be updated or deleted;
  * an approving reviewer may not be the uploader or an author of any annotation;
  * images.training_sequence can only go NULL -> value with one of the two kinds
    of evidence above (TRAINING_GATE_FUNCTION_SQL_V2).
Historical rows (training_sequence already set) are never touched or re-validated.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DDL, DateTime, Index, String, Text, event, text

from app.database import Base

REVIEW_APPROVED, REVIEW_REJECTED = "approved", "rejected"


class LabelReviewImmutableError(Exception):
    pass


class LabelReview(Base):
    __tablename__ = "label_reviews"
    __table_args__ = (
        Index("ix_label_reviews_image_id", "image_id"),
        # one approval per exact revision (idempotent approvals)
        Index("uq_label_reviews_approved_revision", "image_id", "label_sha256", "annotation_fingerprint",
              unique=True, postgresql_where=text("outcome = 'approved'"),
              sqlite_where=text("outcome = 'approved'")),
    )

    review_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    image_id = Column(String(36), nullable=False)          # no FK: evidence outlives image rows
    label_sha256 = Column(String(64), nullable=False)
    annotation_fingerprint = Column(String(64), nullable=False)
    outcome = Column(String(16), nullable=False)            # approved | rejected
    reviewer_id = Column(String(36), nullable=False)
    reviewer_email = Column(String(255), nullable=True)
    annotator_ids = Column(JSON, nullable=False)            # authors at review time (audit)
    ai_involved = Column(Boolean, nullable=False, default=False)
    reason = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


@event.listens_for(LabelReview, "before_update")
def _review_no_update(mapper, connection, target):
    raise LabelReviewImmutableError("label reviews are immutable")


@event.listens_for(LabelReview, "before_delete")
def _review_no_delete(mapper, connection, target):
    raise LabelReviewImmutableError("label reviews cannot be deleted")


LABEL_REVIEW_GUARD_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION zwm_guard_label_reviews() RETURNS trigger AS $$
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        RAISE EXCEPTION 'label reviews are append-only' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.outcome NOT IN ('approved', 'rejected') THEN
        RAISE EXCEPTION 'invalid label review outcome' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.outcome = 'approved' AND (
           EXISTS (SELECT 1 FROM annotations a WHERE a.image_id = NEW.image_id AND a.annotated_by = NEW.reviewer_id)
        OR EXISTS (SELECT 1 FROM images i WHERE i.image_id = NEW.image_id
                   AND (i.user_id = NEW.reviewer_id OR i.label_finalized_by = NEW.reviewer_id))) THEN
        RAISE EXCEPTION 'label approval requires an independent reviewer' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql
"""
LABEL_REVIEW_GUARD_TRIGGER_SQL = (
    "CREATE TRIGGER trg_label_reviews_guard BEFORE INSERT OR UPDATE OR DELETE ON label_reviews "
    "FOR EACH ROW EXECUTE FUNCTION zwm_guard_label_reviews()"
)

TRAINING_GATE_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION zwm_guard_training_eligibility() RETURNS trigger AS $$
BEGIN
    IF NEW.training_sequence IS NOT NULL
       AND (TG_OP = 'INSERT' OR OLD.training_sequence IS NULL)
       AND NOT EXISTS (
            SELECT 1 FROM label_reviews r
            WHERE r.review_id = NEW.training_review_id
              AND r.image_id = NEW.image_id
              AND r.outcome = 'approved'
              AND r.label_sha256 = NEW.label_sha256
              AND r.annotation_fingerprint = NEW.label_fingerprint) THEN
        RAISE EXCEPTION 'training eligibility requires an administrator approval of the exact label revision'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql
"""
# A6.0 completion (migration d9e0f1a2b3c4): A1's user-owned finalization is restored
# for human-only labels. A NULL -> value training_sequence is accepted for exactly two
# kinds of evidence; TRAINING_GATE_FUNCTION_SQL above stays frozen for c8d9e0f1a2b3
# and is what the d9e0f1a2b3c4 downgrade restores.
TRAINING_GATE_FUNCTION_SQL_V2 = """
CREATE OR REPLACE FUNCTION zwm_guard_training_eligibility() RETURNS trigger AS $$
BEGIN
    IF NEW.training_sequence IS NOT NULL
       AND (TG_OP = 'INSERT' OR OLD.training_sequence IS NULL)
       AND NOT (
            -- administrator approval of exactly this revision
            (NEW.label_provenance IS DISTINCT FROM 'user_confirmed' AND EXISTS (
                SELECT 1 FROM label_reviews r
                WHERE r.review_id = NEW.training_review_id
                  AND r.image_id = NEW.image_id
                  AND r.outcome = 'approved'
                  AND r.label_sha256 = NEW.label_sha256
                  AND r.annotation_fingerprint = NEW.label_fingerprint))
            OR
            -- user-confirmed, human-only revision finalized by a person
            (NEW.label_provenance = 'user_confirmed'
             AND NEW.training_review_id IS NULL
             AND NEW.label_sha256 IS NOT NULL
             AND NEW.label_fingerprint IS NOT NULL
             AND NEW.label_finalized_by IS NOT NULL
             AND NEW.ai_suggested_at IS NULL
             AND NOT EXISTS (
                SELECT 1 FROM annotations a
                WHERE a.image_id = NEW.image_id
                  AND (a.ai_generated IS TRUE
                       OR (a.annotated_by IS DISTINCT FROM NEW.user_id
                           AND a.annotated_by IS DISTINCT FROM NEW.label_finalized_by)))
             AND NOT EXISTS (
                SELECT 1 FROM label_reviews r
                WHERE r.image_id = NEW.image_id
                  AND r.outcome = 'rejected'
                  AND r.label_sha256 = NEW.label_sha256
                  AND r.annotation_fingerprint = NEW.label_fingerprint))) THEN
        RAISE EXCEPTION 'training eligibility requires a user-confirmed human label or an administrator approval of the exact label revision'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql
"""
TRAINING_GATE_TRIGGER_SQL = (
    "CREATE TRIGGER trg_images_training_gate BEFORE INSERT OR UPDATE OF training_sequence ON images "
    "FOR EACH ROW EXECUTE FUNCTION zwm_guard_training_eligibility()"
)

event.listen(LabelReview.__table__, "after_create",
             DDL(LABEL_REVIEW_GUARD_FUNCTION_SQL).execute_if(dialect="postgresql"))
event.listen(LabelReview.__table__, "after_create",
             DDL(LABEL_REVIEW_GUARD_TRIGGER_SQL).execute_if(dialect="postgresql"))
ANNOTATION_LOCK_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION zwm_guard_eligible_annotations() RETURNS trigger AS $$
DECLARE
    img_id varchar;
    seq bigint;
BEGIN
    FOREACH img_id IN ARRAY ARRAY[CASE WHEN TG_OP <> 'INSERT' THEN OLD.image_id END,
                                  CASE WHEN TG_OP <> 'DELETE' THEN NEW.image_id END] LOOP
        CONTINUE WHEN img_id IS NULL;
        -- FOR SHARE waits for a concurrent approval holding the row and then sees its result
        SELECT training_sequence INTO seq FROM images WHERE image_id = img_id FOR SHARE;
        IF seq IS NOT NULL THEN
            RAISE EXCEPTION 'annotations of a training-eligible image are locked' USING ERRCODE = 'check_violation';
        END IF;
    END LOOP;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END
$$ LANGUAGE plpgsql
"""
ANNOTATION_LOCK_TRIGGER_SQL = (
    "CREATE TRIGGER trg_annotations_training_lock BEFORE INSERT OR UPDATE OR DELETE ON annotations "
    "FOR EACH ROW EXECUTE FUNCTION zwm_guard_eligible_annotations()"
)

# The images trigger is attached when the images table is created (create_all may
# build label_reviews first); plpgsql resolves label_reviews only at run time.
from app.models.image import Image  # noqa: E402

event.listen(Image.__table__, "after_create",
             DDL(TRAINING_GATE_FUNCTION_SQL_V2).execute_if(dialect="postgresql"))
event.listen(Image.__table__, "after_create",
             DDL(TRAINING_GATE_TRIGGER_SQL).execute_if(dialect="postgresql"))


# ---------------------------------------------------------------------------
# Any annotation change invalidates the finalized (and therefore any approved)
# revision of a not-yet-eligible image: it must be finalized and reviewed again.
# Eligible images are already immutable (annotation_mutation_block_reason).
# ---------------------------------------------------------------------------
from sqlalchemy.orm import object_session  # noqa: E402

from app.models.annotation import Annotation  # noqa: E402

event.listen(Annotation.__table__, "after_create",
             DDL(ANNOTATION_LOCK_FUNCTION_SQL).execute_if(dialect="postgresql"))
event.listen(Annotation.__table__, "after_create",
             DDL(ANNOTATION_LOCK_TRIGGER_SQL).execute_if(dialect="postgresql"))

FINALIZING_KEY = "zwm_a60_finalizing"     # set by finalize while it installs the label


def _invalidate_label_revision(mapper, connection, target):
    session = object_session(target)
    if session is not None and session.info.get(FINALIZING_KEY):
        return
    connection.execute(
        Image.__table__.update()
        .where(Image.__table__.c.image_id == target.image_id)
        .where(Image.__table__.c.training_sequence.is_(None))
        .values(label_sha256=None, label_fingerprint=None, label_finalized_at=None, label_finalized_by=None)
    )


for _evt in ("after_insert", "after_update", "after_delete"):
    event.listen(Annotation, _evt, _invalidate_label_revision)
