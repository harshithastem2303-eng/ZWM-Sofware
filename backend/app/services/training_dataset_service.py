"""
Training dataset foundation (ZWM v1.1.0, Block A1).

Responsibilities
----------------
1. YOLO class mapping   : business Category.class_code -> contiguous YOLO index 0..N-1.
2. Training eligibility : mark an image eligible once annotation + valid YOLO TXT +
                          permanent promotion all succeeded; assign training_sequence.
3. Total threshold      : the configured threshold applies to the TOTAL number of
                          eligible images across all active categories.
4. Milestone snapshots  : cumulative, immutable, exactly-sized dataset snapshots
                          (V1 = T, V2 = V1 + T, ...). Overflow stays outside.

Concurrency
-----------
Eligibility marking and snapshot creation serialize on one transaction-scoped
PostgreSQL advisory lock, so sequence numbers are assigned in commit order and a
milestone can only be locked once. Unique constraints (training_sequence,
milestone_count, version, yolo_class_index) are the hard backstop on any DB.

No training is started from here (Block A2).
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import exists, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.annotation import Annotation
from app.models.category import Category
from app.models.image import Image
from app.models.training import TrainingSnapshot, TrainingSnapshotImage

logger = logging.getLogger(__name__)

# Transaction-scoped advisory lock keys (PostgreSQL only; no-op elsewhere).
_TRAINING_DATASET_LOCK_KEY = 0x5A574D01  # eligibility sequence + snapshot creation
_YOLO_CLASS_MAP_LOCK_KEY = 0x5A574D02    # yolo_class_index assignment

SNAPSHOT_STATUS_LOCKED = "locked"


def _acquire_xact_lock(db: Session, key: int) -> None:
    """Block until the advisory lock is held; released automatically at commit/rollback."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


# ---------------------------------------------------------------------------
# 1. YOLO class mapping
# ---------------------------------------------------------------------------

def ensure_yolo_class_indices(db: Session) -> dict:
    """
    Guarantee every category has a stable YOLO class index and return
    {category_id: yolo_class_index}.

    Unassigned categories receive max+1, max+2, ... in category_id order, so the
    result is deterministic and existing indices are never renumbered.
    Commits only when it assigns something; call without other pending changes.
    """
    if db.query(Category.category_id).filter(Category.yolo_class_index.is_(None)).first() is not None:
        for attempt in range(3):
            try:
                _acquire_xact_lock(db, _YOLO_CLASS_MAP_LOCK_KEY)
                missing = (
                    db.query(Category)
                    .filter(Category.yolo_class_index.is_(None))
                    .order_by(Category.category_id)
                    .all()
                )
                max_index = db.query(func.max(Category.yolo_class_index)).scalar()
                next_index = 0 if max_index is None else max_index + 1
                for cat in missing:
                    cat.yolo_class_index = next_index
                    logger.info(
                        "YOLO_CLASS_INDEX_ASSIGNED | category_id=%s | class_code=%s | yolo_index=%s",
                        cat.category_id, cat.class_code, next_index,
                    )
                    next_index += 1
                db.commit()
                break
            except IntegrityError:
                db.rollback()
                if attempt == 2:
                    raise

    return {
        cid: idx
        for cid, idx in db.query(Category.category_id, Category.yolo_class_index).all()
    }


def get_yolo_class_index(db: Session, category_id: Optional[int]) -> Optional[int]:
    """YOLO index for a category, or None if the category does not exist."""
    if category_id is None:
        return None
    return ensure_yolo_class_indices(db).get(category_id)


class ClassMapIntegrityError(Exception):
    pass


def get_class_map(db: Session) -> list:
    """
    Frozen-able class map ordered by YOLO index. Includes archived (inactive)
    categories so indices stay contiguous 0..N-1. Raises if a gap exists.
    """
    ensure_yolo_class_indices(db)
    cats = db.query(Category).order_by(Category.yolo_class_index).all()
    indices = [c.yolo_class_index for c in cats]
    if indices != list(range(len(indices))):
        raise ClassMapIntegrityError(f"YOLO class indices are not contiguous 0..N-1: {indices}")
    return [
        {
            "yolo_index": c.yolo_class_index,
            "category_id": c.category_id,
            "class_code": c.class_code,
            "class_name": c.class_name,
            "is_active": bool(c.is_active),
        }
        for c in cats
    ]


def read_yolo_class_ids(txt_path: str) -> Optional[list]:
    """Return class ids from a YOLO TXT, or None if unreadable/malformed."""
    try:
        with open(txt_path, "r") as fh:
            lines = [l.strip() for l in fh if l.strip()]
        return [int(l.split()[0]) for l in lines] if lines else None
    except (OSError, ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# 2. Training eligibility
# ---------------------------------------------------------------------------

def eligible_images_query(db: Session):
    """
    Images that count toward training milestones.

    Eligibility is HISTORICAL: once an image received a training_sequence it
    counts forever, independent of later category archiving or status changes.
    This guarantees V1 subset of V2 subset of V3 ... (cumulative snapshots).
    Gate-keeping of NEW eligibility happens in evaluate_training_eligibility().
    """
    return db.query(Image).filter(
        Image.training_sequence.isnot(None),
        Image.training_eligible_at.isnot(None),
    )


def evaluate_training_eligibility(db: Session, image: Image) -> tuple:
    """
    Label readiness AND one kind of human evidence for exactly the current, finalized
    label revision. Returns (eligible, reason).

    * user_confirmed (A1): a human-only revision finalized by a person -- no
      AI-generated annotation, no AI suggestions served for the image, every
      annotation by the owner or the finalizer, never rejected;
    * admin_approved (A6.0): an independent administrator approved the revision.
      Required whenever the user-confirmed conditions do not hold.

    AI auto-acceptance (Image.is_validated / validation_result) is never evidence.
    """
    ready, reason = evaluate_label_readiness(db, image)
    if not ready:
        return False, reason
    review, why = current_label_approval(db, image)
    if review is not None:
        return True, "ok"
    if why != "label_not_reviewed":                     # not finalized / changed since finalize
        return False, why
    problem = user_confirmation_problem(db, image)
    if problem is None:
        return True, "ok"
    return False, "label_rejected" if problem == "label_rejected" else "label_not_reviewed"


def evaluate_label_readiness(db: Session, image: Image) -> tuple:
    """
    Structural label checks (pre-A6.0 eligibility rules): permanent image, valid
    annotation set, active categories, valid YOLO label. Returns (ready, reason).
    """

    if image is None:
        return False, "image_missing"
    if image.status != "permanent" or not image.permanent_s3_path or not os.path.isfile(image.permanent_s3_path):
        return False, "not_promoted_to_permanent"

    annotations = db.query(Annotation).filter(Annotation.image_id == image.image_id).all()
    if not annotations:
        return False, "no_annotation"
    if not any(a.annotation_type and a.label_data_json for a in annotations):
        return False, "no_valid_annotation"

    active_ids = {
        cid for (cid,) in db.query(Category.category_id).filter(Category.is_active.is_(True)).all()
    }
    for a in annotations:
        cid = a.category_id if a.category_id is not None else image.selected_category_id
        if cid is None or cid not in active_ids:
            return False, "invalid_or_inactive_category"

    problem = yolo_label_problem(db, image.yolo_txt_path)
    if problem:
        return False, problem

    return True, "ok"


def yolo_label_problem(db: Session, txt_path: Optional[str]) -> Optional[str]:
    """None if the TXT is valid and only uses YOLO indices of ACTIVE categories."""
    from app.services.lifecycle_service import validate_yolo_txt

    if not txt_path or not validate_yolo_txt(txt_path):
        return "missing_or_invalid_yolo_label"
    # Read-only lookup: may run inside a caller's transaction, so never commit here.
    class_ids = read_yolo_class_ids(txt_path)
    valid_indices = {
        idx for (idx,) in db.query(Category.yolo_class_index).filter(
            Category.is_active.is_(True), Category.yolo_class_index.isnot(None)
        ).all()
    }
    if not class_ids or any(c not in valid_indices for c in class_ids):
        return "yolo_class_id_not_mapped"
    return None


def mark_training_eligible(db: Session, image: Image, now: Optional[datetime] = None) -> bool:
    """
    Flag the image as training eligible and assign the next training_sequence.

    Must run inside the caller's transaction; the caller commits. Takes the
    training-dataset advisory lock so sequence order == commit order.
    Idempotent: an image keeps its first sequence forever.
    """
    if image.training_sequence is not None:
        return True

    eligible, reason = evaluate_training_eligibility(db, image)
    if not eligible:
        logger.info("TRAINING_NOT_ELIGIBLE | image_id=%s | reason=%s", image.image_id, reason)
        return False

    _acquire_xact_lock(db, _TRAINING_DATASET_LOCK_KEY)
    review, _ = current_label_approval(db, image)
    max_seq = db.query(func.max(Image.training_sequence)).scalar()
    # A6.0: the evidence is recorded on the row and re-checked by the DB gate trigger
    if review is not None:
        image.training_review_id, image.label_provenance = review.review_id, PROVENANCE_ADMIN_APPROVED
    else:
        image.training_review_id, image.label_provenance = None, PROVENANCE_USER_CONFIRMED
    image.training_sequence = (max_seq or 0) + 1
    image.training_eligible_at = now or datetime.now(timezone.utc)
    logger.info(
        "TRAINING_ELIGIBLE | image_id=%s | training_sequence=%s",
        image.image_id, image.training_sequence,
    )
    return True


# ---------------------------------------------------------------------------
# 3. Total threshold / next milestone
# ---------------------------------------------------------------------------

def get_training_threshold(db: Session) -> int:
    """Admin-configured number of NEW eligible images per milestone (>= 1)."""
    from app.models.setting import SystemSetting

    sys_setting = db.query(SystemSetting).filter(SystemSetting.id == 1).first()
    value = sys_setting.auto_retrain_count if sys_setting and sys_setting.auto_retrain_count else None
    if not value or value < 1:
        value = settings.CATEGORY_VALIDATED_THRESHOLD
    return max(1, int(value))


def count_training_eligible_images(db: Session) -> int:
    return eligible_images_query(db).count()


def get_last_milestone(db: Session) -> int:
    return db.query(func.max(TrainingSnapshot.milestone_count)).scalar() or 0


def get_training_progress(db: Session) -> dict:
    """
    next_milestone = last locked milestone + CURRENT threshold.
    A threshold change only affects milestones not yet locked.
    """
    total = count_training_eligible_images(db)
    threshold = get_training_threshold(db)
    last_milestone = get_last_milestone(db)
    next_milestone = last_milestone + threshold
    return {
        "total_training_eligible_images": total,
        "threshold": threshold,
        "last_milestone": last_milestone,
        "next_milestone": next_milestone,
        "remaining_to_next_milestone": max(0, next_milestone - total),
        "images_since_last_milestone": max(0, total - last_milestone),
        "ready": total >= next_milestone,
        "snapshot_count": db.query(func.count(TrainingSnapshot.snapshot_id)).scalar() or 0,
    }


def get_eligible_counts_by_category(db: Session) -> dict:
    """{category_id: eligible image count} for informational stats only."""
    rows = (
        eligible_images_query(db)
        .with_entities(Image.selected_category_id, func.count(Image.image_id))
        .group_by(Image.selected_category_id)
        .all()
    )
    return {cid: n for cid, n in rows}


# ---------------------------------------------------------------------------
# 4. Milestone snapshots
# ---------------------------------------------------------------------------

def create_next_snapshot_if_ready(db: Session) -> Optional[TrainingSnapshot]:
    """
    Lock the next cumulative milestone if enough eligible images exist.

    Selects exactly ``next_milestone`` images by training_sequence; anything
    beyond stays outside as overflow. Creates at most ONE snapshot per call.
    Returns the new snapshot, or None (not ready / already created concurrently).
    Call with no other pending changes on the session.
    """
    try:
        ensure_yolo_class_indices(db)
        _acquire_xact_lock(db, _TRAINING_DATASET_LOCK_KEY)

        # Re-evaluate under the lock so concurrent callers see each other's work.
        progress = get_training_progress(db)
        if not progress["ready"]:
            db.rollback()
            return None

        milestone = progress["next_milestone"]
        rows = (
            eligible_images_query(db)
            .with_entities(Image.image_id, Image.training_sequence, Image.yolo_txt_path)
            .order_by(Image.training_sequence.asc())
            .limit(milestone)
            .all()
        )
        if len(rows) != milestone:
            db.rollback()
            return None

        version = (db.query(func.max(TrainingSnapshot.version)).scalar() or 0) + 1
        snapshot = TrainingSnapshot(
            version=version,
            threshold=progress["threshold"],
            milestone_count=milestone,
            dataset_size=len(rows),
            first_sequence=rows[0].training_sequence,
            last_sequence=rows[-1].training_sequence,
            class_map=get_class_map(db),
            status=SNAPSHOT_STATUS_LOCKED,
        )
        from app.services.training_pipeline_service import (
            assign_splits_for_new_snapshot,
            create_auto_job_for_snapshot,
        )
        # 80/10/10 assignment is frozen with the membership (inherited for old images).
        splits = assign_splits_for_new_snapshot(db, rows)
        db.add(snapshot)
        db.flush()
        db.add_all(
            TrainingSnapshotImage(
                snapshot_id=snapshot.snapshot_id,
                image_id=r.image_id,
                position=pos,
                training_sequence=r.training_sequence,
                split_type=splits[r.image_id],
            )
            for pos, r in enumerate(rows)
        )
        # Durable outbox: the automatic training job commits atomically with the snapshot.
        create_auto_job_for_snapshot(db, snapshot)
        db.commit()
        db.refresh(snapshot)
        logger.info(
            "TRAINING_SNAPSHOT_LOCKED | version=V%s | milestone=%s | size=%s | threshold=%s | overflow=%s",
            snapshot.version, milestone, snapshot.dataset_size, snapshot.threshold,
            progress["total_training_eligible_images"] - milestone,
        )
        return snapshot
    except IntegrityError:
        # Another worker locked this milestone first (unique milestone_count/version).
        db.rollback()
        logger.info("TRAINING_SNAPSHOT_DUPLICATE_SKIPPED | milestone already locked")
        return None
    except Exception:
        db.rollback()
        raise


def reconcile_training_snapshots(db: Session, max_snapshots: int = 50) -> list:
    """
    Lock every milestone that is currently reached but not yet snapshotted.

    Safe to call any number of times (promotion hook, admin endpoint, Block A2
    trigger): a failed earlier attempt is simply retried, and each milestone is
    locked exactly once with exactly ``milestone_count`` images.
    """
    created = []
    for _ in range(max_snapshots):
        snapshot = create_next_snapshot_if_ready(db)
        if snapshot is None:
            break
        created.append(snapshot)
    return created


def image_deletion_block_reason(db: Session, image: Image) -> Optional[str]:
    """Why an image must not be hard-deleted, or None if deletion is allowed."""
    in_snapshot = db.query(
        exists().where(TrainingSnapshotImage.image_id == image.image_id)
    ).scalar()
    if in_snapshot:
        return "Image is part of a locked training snapshot and cannot be deleted"
    if image.training_sequence is not None:
        return "Image is training eligible and counts toward the next training milestone; it cannot be deleted"
    return None


def lock_training_dataset(db: Session) -> None:
    """Serialize with eligibility marking and snapshot creation (held until commit/rollback)."""
    _acquire_xact_lock(db, _TRAINING_DATASET_LOCK_KEY)


def is_in_snapshot(db: Session, image_id: str) -> bool:
    return bool(db.query(exists().where(TrainingSnapshotImage.image_id == image_id)).scalar())


def annotation_mutation_block_reason(db: Session, image: Optional[Image]) -> Optional[str]:
    """Why annotations of this image must not be updated/deleted, or None."""
    if image is None:
        return None
    if is_in_snapshot(db, image.image_id):
        return "Annotation belongs to an image locked in a training snapshot and cannot be changed"
    if image.training_sequence is not None:
        return "Annotation belongs to a training-eligible image and cannot be changed"
    return None


def annotation_append_block_reason(db: Session, image: Image) -> Optional[str]:
    """
    New annotations may be added while labeling is in progress. Once the image is
    finalized (training eligible) or locked in a snapshot, its annotation set is frozen.
    """
    if is_in_snapshot(db, image.image_id):
        return "Image is locked in a training snapshot; new annotations cannot be added"
    if image.training_sequence is not None:
        return "Image labeling is finalized; its annotation set is frozen"
    return None


def category_has_training_history(category: Category) -> bool:
    """A category that owns a YOLO class index must be archived, never hard-deleted."""
    return category.yolo_class_index is not None


def get_snapshot_image_ids(db: Session, snapshot_id: int) -> list:
    return [
        image_id
        for (image_id,) in db.query(TrainingSnapshotImage.image_id)
        .filter(TrainingSnapshotImage.snapshot_id == snapshot_id)
        .order_by(TrainingSnapshotImage.position)
        .all()
    ]


def snapshot_to_dict(snapshot: TrainingSnapshot) -> dict:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "version": f"V{snapshot.version}",
        "threshold": snapshot.threshold,
        "milestone_count": snapshot.milestone_count,
        "dataset_size": snapshot.dataset_size,
        "first_sequence": snapshot.first_sequence,
        "last_sequence": snapshot.last_sequence,
        "class_map": snapshot.class_map,
        "status": snapshot.status,
        "created_at": str(snapshot.created_at) if snapshot.created_at else None,
    }


# ---------------------------------------------------------------------------
# 5. Finish-labeling boundary (multi-object images)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Human label review (Block A6.0)
# ---------------------------------------------------------------------------

class LabelReviewError(Exception):
    """Review refused. ``status`` maps to the HTTP status code."""

    def __init__(self, reason: str, status: int = 409):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def file_sha256(path: Optional[str]) -> Optional[str]:
    import hashlib
    if not path or not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def annotation_fingerprint(db: Session, image_id: str) -> str:
    """SHA-256 over the canonical annotation set (any add/edit/delete changes it)."""
    import hashlib
    import json
    rows = db.query(Annotation).filter(Annotation.image_id == image_id).order_by(Annotation.annotation_id).all()
    canon = [[a.annotation_id, a.category_id, a.annotation_type, a.label_data_json, bool(a.ai_generated),
              a.annotated_by] for a in rows]
    return hashlib.sha256(json.dumps(canon, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _finalized_revision_is_current(db: Session, image: Image) -> bool:
    return bool(image.label_sha256 and image.label_fingerprint
                and file_sha256(image.yolo_txt_path) == image.label_sha256
                and annotation_fingerprint(db, image.image_id) == image.label_fingerprint)


def current_label_approval(db: Session, image: Image) -> tuple:
    """
    (LabelReview, "ok") when an approved review covers exactly the image's current,
    finalized label revision; otherwise (None, reason). Recomputed from the label
    file and the annotation rows every time -- stored flags are never trusted alone.
    """
    from app.models.label_review import REVIEW_APPROVED, LabelReview

    if not image.label_sha256 or not image.label_fingerprint:
        return None, "label_not_finalized"
    if not _finalized_revision_is_current(db, image):
        return None, "label_changed_since_finalize"
    review = (db.query(LabelReview)
              .filter(LabelReview.image_id == image.image_id, LabelReview.outcome == REVIEW_APPROVED,
                      LabelReview.label_sha256 == image.label_sha256,
                      LabelReview.annotation_fingerprint == image.label_fingerprint)
              .order_by(LabelReview.reviewed_at.desc()).first())
    if review is None:
        return None, "label_not_reviewed"
    return review, "ok"


PROVENANCE_USER_CONFIRMED, PROVENANCE_ADMIN_APPROVED = "user_confirmed", "admin_approved"


def user_confirmation_problem(db: Session, image: Image) -> Optional[str]:
    """
    None when the current finalized revision may become eligible on the strength of
    its own human finalization (A1); otherwise why an administrator must review it.
    Everything is recomputed from rows and the label file (mirrors the DB trigger).
    """
    from app.models.label_review import REVIEW_REJECTED, LabelReview

    if not image.label_sha256 or not image.label_fingerprint:
        return "label_not_finalized"
    if not _finalized_revision_is_current(db, image):
        return "label_changed_since_finalize"
    if not image.label_finalized_by:
        return "not_finalized_by_a_person"
    if image.ai_suggested_at is not None:
        return "ai_suggestions_served"
    allowed = {image.user_id, image.label_finalized_by}
    for ai_generated, author in db.query(Annotation.ai_generated, Annotation.annotated_by).filter(
            Annotation.image_id == image.image_id).all():
        if ai_generated:
            return "ai_generated_annotations"
        if author not in allowed:
            return "foreign_annotations"
    rejected = db.query(exists().where(
        LabelReview.image_id == image.image_id, LabelReview.outcome == REVIEW_REJECTED,
        LabelReview.label_sha256 == image.label_sha256,
        LabelReview.annotation_fingerprint == image.label_fingerprint)).scalar()
    if rejected:
        return "label_rejected"
    return None


def record_ai_suggestion(db: Session, image_id: Optional[str]) -> None:
    """
    Server-side evidence that AI suggestions were served for ``image_id`` (Block A6.0).
    Committed BEFORE the suggestions are returned, so no later revision of the image
    can be user-confirmed: it needs an administrator review. Never touches eligible rows.
    """
    if not image_id:
        return
    db.query(Image).filter(Image.image_id == image_id, Image.training_sequence.is_(None),
                           Image.ai_suggested_at.is_(None)).update(
        {"ai_suggested_at": datetime.now(timezone.utc)}, synchronize_session=False)
    db.commit()


def label_authors(db: Session, image: Image) -> dict:
    """Everyone who contributed to the label revision (ids + emails, lower-cased)."""
    from app.models.user import User
    ids = {a for (a,) in db.query(Annotation.annotated_by).filter(Annotation.image_id == image.image_id).all() if a}
    ids |= {i for i in (image.user_id, image.label_finalized_by) if i}
    emails = {e.lower() for (e,) in db.query(User.email).filter(User.user_id.in_(ids)).all() if e} if ids else set()
    ai = bool(db.query(exists().where(Annotation.image_id == image.image_id,
                                      Annotation.ai_generated.is_(True))).scalar())
    return {"ids": ids, "emails": emails, "ai_involved": ai}


def label_review_state(db: Session, image: Image) -> dict:
    """Read-only review status for the admin UI / API (no paths)."""
    from app.models.label_review import LabelReview
    authors = label_authors(db, image)
    review, why = current_label_approval(db, image)
    history = (db.query(LabelReview).filter(LabelReview.image_id == image.image_id)
               .order_by(LabelReview.reviewed_at.desc()).all())
    return {
        "image_id": image.image_id,
        "label_sha256": image.label_sha256,
        "label_finalized_at": image.label_finalized_at.isoformat() if image.label_finalized_at else None,
        "finalized_revision_current": _finalized_revision_is_current(db, image),
        "ai_involved": authors["ai_involved"],
        "annotation_count": db.query(func.count(Annotation.annotation_id))
                              .filter(Annotation.image_id == image.image_id).scalar() or 0,
        "training_eligible": image.training_sequence is not None,
        "training_sequence": image.training_sequence,
        "label_provenance": image.label_provenance,
        "requires_review": image.training_sequence is None and review is None
                           and user_confirmation_problem(db, image) is not None,
        "review_reason": None if image.training_sequence is not None else user_confirmation_problem(db, image),
        "approved": review is not None,
        "status": "eligible" if image.training_sequence is not None else why,
        "reviews": [{"review_id": r.review_id, "outcome": r.outcome, "label_sha256": r.label_sha256,
                     "reviewer_id": r.reviewer_id, "reason": r.reason, "ai_involved": r.ai_involved,
                     "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None} for r in history],
    }


def review_label_revision(
    db: Session,
    image_id: str,
    *,
    reviewer_id: str,
    reviewer_email: Optional[str],
    decision: str,
    label_sha256: str,
    reason: Optional[str] = None,
    reconcile: bool = True,
) -> dict:
    """
    Administrator decision on ONE exact label revision (Block A6.0).

    approved -> append an approved LabelReview and, in the same transaction and under
                the training-dataset lock, assign the training sequence;
    rejected -> append a rejected LabelReview (the image stays ineligible).

    Refused (LabelReviewError) when the revision is not finalized, changed since
    finalize, differs from ``label_sha256`` (stale screen), or the reviewer is the
    uploader / finalizer / an annotation author. Idempotent for repeated approvals.
    """
    from app.models.label_review import REVIEW_APPROVED, REVIEW_REJECTED, LabelReview

    if decision not in (REVIEW_APPROVED, REVIEW_REJECTED):
        raise LabelReviewError("decision must be 'approved' or 'rejected'", 422)
    if not reviewer_id:
        raise LabelReviewError("reviewer identity required", 422)

    lock_training_dataset(db)
    image = (db.query(Image).filter(Image.image_id == image_id)
             .with_for_update(of=Image).populate_existing().first())
    if image is None:
        db.rollback()
        raise LabelReviewError("image_not_found", 404)
    if image.training_sequence is not None:
        seq = image.training_sequence
        db.rollback()
        if decision == REVIEW_APPROVED:
            return {"image_id": image_id, "decision": decision, "created": False,
                    "training_eligible": True, "training_sequence": seq, "snapshots_created": []}
        raise LabelReviewError("image is already training eligible; its labels are locked")
    if not image.label_sha256 or not image.label_fingerprint:
        db.rollback()
        raise LabelReviewError("label_not_finalized")
    if not _finalized_revision_is_current(db, image):
        db.rollback()
        raise LabelReviewError("label_changed_since_finalize")
    if label_sha256 != image.label_sha256:
        db.rollback()
        raise LabelReviewError("stale_label_revision")

    authors = label_authors(db, image)
    if reviewer_id in authors["ids"] or (reviewer_email and reviewer_email.lower() in authors["emails"]):
        db.rollback()
        raise LabelReviewError("reviewer_not_independent", 403)

    if decision == REVIEW_APPROVED:
        ready, why = evaluate_label_readiness(db, image)
        if not ready:
            db.rollback()
            raise LabelReviewError(why)
        existing, _ = current_label_approval(db, image)
        review = existing or LabelReview(
            image_id=image_id, label_sha256=image.label_sha256, annotation_fingerprint=image.label_fingerprint,
            outcome=REVIEW_APPROVED, reviewer_id=reviewer_id, reviewer_email=reviewer_email,
            annotator_ids=sorted(authors["ids"]), ai_involved=authors["ai_involved"], reason=reason)
        if existing is None:
            db.add(review)
            db.flush()
        if not mark_training_eligible(db, image):
            db.rollback()
            raise LabelReviewError("label_not_eligible")
        db.commit()
        db.refresh(image)
        logger.info("LABEL_APPROVED | image_id=%s | review_id=%s | training_sequence=%s | ai_involved=%s",
                    image_id, review.review_id, image.training_sequence, authors["ai_involved"])
        created = []
        if reconcile:
            try:
                created = [snap.version for snap in reconcile_training_snapshots(db)]
            except Exception as exc:  # recoverable via POST /api/dataset/snapshots/reconcile
                logger.error("TRAINING_SNAPSHOT_CHECK_FAILED | image_id=%s | %s", image_id, exc)
        return {"image_id": image_id, "decision": decision, "created": existing is None,
                "review_id": review.review_id, "training_eligible": True,
                "training_sequence": image.training_sequence, "snapshots_created": created}

    review = LabelReview(
        image_id=image_id, label_sha256=image.label_sha256, annotation_fingerprint=image.label_fingerprint,
        outcome=REVIEW_REJECTED, reviewer_id=reviewer_id, reviewer_email=reviewer_email,
        annotator_ids=sorted(authors["ids"]), ai_involved=authors["ai_involved"], reason=reason)
    db.add(review)
    db.commit()
    logger.info("LABEL_REJECTED | image_id=%s | review_id=%s", image_id, review.review_id)
    return {"image_id": image_id, "decision": decision, "created": True, "review_id": review.review_id,
            "training_eligible": False, "training_sequence": None, "snapshots_created": []}


def pending_label_reviews(db: Session, limit: int = 50, offset: int = 0) -> dict:
    """Finalized, not yet eligible images whose current revision has no decision yet."""
    from app.models.label_review import LabelReview
    q = db.query(Image).filter(Image.training_sequence.is_(None), Image.label_sha256.isnot(None),
                               Image.label_fingerprint.isnot(None))
    decided = (db.query(LabelReview.image_id)
               .filter(LabelReview.image_id == Image.image_id, LabelReview.label_sha256 == Image.label_sha256,
                       LabelReview.annotation_fingerprint == Image.label_fingerprint))
    q = q.filter(~decided.exists())
    total = q.count()
    rows = q.order_by(Image.label_finalized_at, Image.image_id).offset(offset).limit(limit).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [{**label_review_state(db, img), "original_filename": img.original_filename,
                       "user_id": img.user_id, "selected_category_id": img.selected_category_id} for img in rows]}


class LabelingFinalizationError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def annotation_set_problem(db: Session, image: Image) -> Optional[str]:
    """None if every annotation of the image is a complete, labelable object."""
    from app.services.annotation_converter import shape_to_bbox

    annotations = db.query(Annotation).filter(Annotation.image_id == image.image_id).all()
    if not annotations:
        return "no_annotations"
    active_ids = {
        cid for (cid,) in db.query(Category.category_id).filter(Category.is_active.is_(True)).all()
    }
    for a in annotations:
        if not a.annotation_type or not a.label_data_json:
            return f"invalid_annotation:{a.annotation_id}"
        if shape_to_bbox(a.annotation_type, a.label_data_json) is None:
            return f"invalid_geometry:{a.annotation_id}"
        cid = a.category_id if a.category_id is not None else image.selected_category_id
        if cid is None or cid not in active_ids:
            return f"invalid_or_inactive_category:{a.annotation_id}"
    return None


def _count_label_lines(txt_path: Optional[str]) -> int:
    try:
        with open(txt_path, "r") as fh:
            return sum(1 for line in fh if line.strip())
    except (OSError, TypeError):
        return 0


def _install_label(perm_txt: str, new_txt: str, preserve_previous_as: Optional[str]) -> str:
    """Atomically replace the permanent label; returns a rollback backup path."""
    import shutil

    if preserve_previous_as:
        keep = perm_txt + preserve_previous_as
        if not os.path.exists(keep):  # never overwrite an earlier recovery copy
            shutil.copy2(perm_txt, keep)
    backup = perm_txt + ".finalize.bak"
    shutil.copy2(perm_txt, backup)
    tmp = perm_txt + ".tmp"
    shutil.copy2(new_txt, tmp)
    os.replace(tmp, perm_txt)
    return backup


def _may_grant(db: Session, image: Image, allow_user_confirmed: bool) -> bool:
    if not evaluate_training_eligibility(db, image)[0]:
        return False
    return allow_user_confirmed or current_label_approval(db, image)[0] is not None


def finalize_image_labeling(
    db: Session,
    image_id: str,
    *,
    preserve_previous_label_as: Optional[str] = None,
    reconcile: bool = True,
    finalized_by: Optional[str] = None,
    allow_user_confirmed: bool = True,
) -> dict:
    """
    Explicit finish-labeling step (A1), with A6.0 provenance rules.

    1. Validate the complete annotation set (every object, active category).
    2. Promote to permanent storage if not yet promoted.
    3. Under the training-dataset lock: regenerate the YOLO label from ALL
       annotations, verify one line per annotation, install it atomically (only
       inside UPLOAD_FOLDER) and pin the revision (label SHA-256 + annotation
       fingerprint) on the image.
    4. A human-only revision finalized by a person becomes training eligible in the
       same transaction (user_confirmed, A1). Any AI involvement or foreign
       annotation leaves it awaiting an independent administrator review.

    ``finalized_by`` defaults to the image owner for internal callers (backfill).
    ``allow_user_confirmed=False`` (A6.3 revision activation): the revision is pinned
    but only an administrator approval of exactly this revision can make it eligible.
    Idempotent: an eligible image returns its sequence; an unchanged finalized
    revision is returned as already finalized (and granted if it now qualifies).
    Raises LabelingFinalizationError(reason).
    """
    from app.routes.annotation import _generate_yolo_txt_for_image
    from app.services.lifecycle_service import promote_to_permanent

    def _already(img, created=()):
        return {
            "image_id": img.image_id,
            "finalized": True,
            "already_finalized": True,
            "training_eligible": img.training_sequence is not None,
            "awaiting_review": img.training_sequence is None,
            "label_sha256": img.label_sha256,
            "label_provenance": img.label_provenance,
            "training_sequence": img.training_sequence,
            "snapshots_created": list(created),
        }

    def _reconcile():
        if not reconcile:
            return []
        try:
            return [snap.version for snap in reconcile_training_snapshots(db)]
        except Exception as exc:  # recoverable via POST /api/dataset/snapshots/reconcile
            logger.error("TRAINING_SNAPSHOT_CHECK_FAILED | image_id=%s | %s", image_id, exc)
            return []

    image = db.query(Image).filter(Image.image_id == image_id).first()
    if image is None:
        raise LabelingFinalizationError("image_not_found")
    finalized_by = finalized_by or image.user_id
    if image.training_sequence is not None:
        return _already(image)
    if _finalized_revision_is_current(db, image):
        # Unchanged revision finalized earlier (e.g. while review was mandatory):
        # grant it now if it is a user-confirmed human label; otherwise it waits.
        lock_training_dataset(db)
        image = db.query(Image).filter(Image.image_id == image_id).populate_existing().one()
        if image.training_sequence is None and _may_grant(db, image, allow_user_confirmed):
            mark_training_eligible(db, image)
            db.commit()
            db.refresh(image)
            return _already(image, _reconcile())
        db.rollback()
        return _already(image)

    problem = annotation_set_problem(db, image)
    if problem:
        raise LabelingFinalizationError(problem)

    ensure_yolo_class_indices(db)  # may commit; must run before taking the lock

    if image.status != "permanent":
        # Row lock serializes concurrent promotions of the same image (released by
        # promote_to_permanent's commit); a second caller then sees 'permanent'.
        db.query(Image).filter(Image.image_id == image_id).with_for_update().populate_existing().one()
        txt = _generate_yolo_txt_for_image(image_id, db)
        if not txt:
            db.rollback()
            raise LabelingFinalizationError("yolo_generation_failed")
        result = promote_to_permanent(db, image_id, txt)
        if not result.get("success"):
            db.rollback()
            raise LabelingFinalizationError(f"promotion_failed: {result.get('message')}")

    lock_training_dataset(db)
    image = db.query(Image).filter(Image.image_id == image_id).populate_existing().one()
    if image.training_sequence is not None or _finalized_revision_is_current(db, image):  # concurrent
        db.rollback()
        return _already(image)

    problem = annotation_set_problem(db, image)
    expected_lines = db.query(Annotation).filter(Annotation.image_id == image_id).count()
    txt = None if problem else _generate_yolo_txt_for_image(image_id, db)
    if not problem and _count_label_lines(txt) != expected_lines:
        problem = "incomplete_yolo_label"
    if not problem:
        problem = yolo_label_problem(db, txt)
    perm_txt = image.yolo_txt_path
    if not problem and (not perm_txt or not os.path.isfile(perm_txt)):
        problem = "missing_permanent_label"
    if problem:
        db.rollback()
        raise LabelingFinalizationError(problem)

    # Database-stored paths are never trusted: the label is replaced (and the generated
    # copy removed) only inside the configured upload root (A5.1 confinement).
    from app.services.fs_safety import UnsafeFilesystemOperation, assert_within, remove_file_within
    try:
        assert_within(perm_txt, settings.UPLOAD_FOLDER, action="replace label")
        assert_within(txt, settings.UPLOAD_FOLDER, action="read generated label")
    except UnsafeFilesystemOperation as exc:
        db.rollback()
        logger.error("UNSAFE_LABEL_PATH_REFUSED | image_id=%s | %s", image_id, exc)
        raise LabelingFinalizationError("unsafe_label_path")

    from app.models.label_review import FINALIZING_KEY

    backup = _install_label(perm_txt, txt, preserve_previous_label_as)
    db.info[FINALIZING_KEY] = True
    try:
        ready, reason = evaluate_label_readiness(db, image)
        if not ready:
            raise LabelingFinalizationError(reason)
        image.label_sha256 = file_sha256(perm_txt)                # A6.0: pin the exact revision
        image.label_fingerprint = annotation_fingerprint(db, image_id)
        image.label_finalized_at = datetime.now(timezone.utc)
        image.label_finalized_by = finalized_by
        if _may_grant(db, image, allow_user_confirmed):        # user-confirmed human label (A1)
            mark_training_eligible(db, image)
        db.commit()
    except IntegrityError:
        # Unique training_sequence backstop: another worker finalized concurrently.
        db.rollback()
        os.replace(backup, perm_txt)
        image = db.query(Image).filter(Image.image_id == image_id).populate_existing().one()
        if image.training_sequence is not None:
            return _already(image)
        raise
    except Exception:
        db.rollback()
        os.replace(backup, perm_txt)
        raise
    finally:
        db.info.pop(FINALIZING_KEY, None)
    os.remove(backup)
    if txt != perm_txt:
        remove_file_within(txt, settings.UPLOAD_FOLDER, logger)
    db.refresh(image)
    eligible = image.training_sequence is not None
    logger.info(
        "IMAGE_LABELING_FINALIZED | image_id=%s | label_sha256=%s | objects=%s | %s",
        image_id, image.label_sha256, expected_lines,
        f"training_sequence={image.training_sequence} ({image.label_provenance})" if eligible
        else f"awaiting administrator review ({user_confirmation_problem(db, image)})",
    )
    return {
        "image_id": image_id,
        "finalized": True,
        "already_finalized": False,
        "training_eligible": eligible,
        "awaiting_review": not eligible,
        "label_sha256": image.label_sha256,
        "label_provenance": image.label_provenance,
        "training_sequence": image.training_sequence,
        "snapshots_created": _reconcile() if eligible else [],
    }


# ---------------------------------------------------------------------------
# 6. Historical (pre-A1) permanent image audit + explicit backfill
# ---------------------------------------------------------------------------

AUDIT_READY = "ready"                                  # labels already use YOLO indices
AUDIT_LEGACY_CODES = "legacy_class_codes"              # labels use business class_code
AUDIT_MISMATCH = "label_annotation_mismatch"           # TXT disagrees with DB annotations
AUDIT_ELIGIBLE = "already_eligible"
_BACKFILL_DEFAULT = (AUDIT_READY, AUDIT_LEGACY_CODES)
PRE_A1_LABEL_SUFFIX = ".pre_a1.bak"


def audit_historical_images(db: Session) -> dict:
    """
    READ-ONLY classification of every permanent image. Never writes DB or files.
    """
    index_map = {cid: idx for cid, idx in db.query(Category.category_id, Category.yolo_class_index).all()}
    code_map = {cid: code for cid, code in db.query(Category.category_id, Category.class_code).all()}
    snapshot_ids = {iid for (iid,) in db.query(TrainingSnapshotImage.image_id).distinct().all()}

    records = []
    images = (
        db.query(Image)
        .filter(Image.status == "permanent")
        .order_by(Image.permanent_at.asc(), Image.image_id.asc())
        .all()
    )
    for img in images:
        rec = {
            "image_id": img.image_id,
            "training_sequence": img.training_sequence,
            "in_snapshot": img.image_id in snapshot_ids,
        }
        if img.training_sequence is not None:
            rec["classification"] = AUDIT_ELIGIBLE
        elif not img.permanent_s3_path or not os.path.isfile(img.permanent_s3_path):
            rec["classification"] = "missing_image_file"
        elif annotation_set_problem(db, img):
            rec["classification"] = annotation_set_problem(db, img).split(":")[0]
        elif not img.yolo_txt_path or not os.path.isfile(img.yolo_txt_path):
            rec["classification"] = "missing_label_file"
        else:
            anns = db.query(Annotation).filter(Annotation.image_id == img.image_id).all()
            cids = [a.category_id if a.category_id is not None else img.selected_category_id for a in anns]
            found = sorted(read_yolo_class_ids(img.yolo_txt_path) or [])
            expected_idx = sorted(index_map.get(c) for c in cids) if all(index_map.get(c) is not None for c in cids) else None
            expected_codes = sorted(code_map.get(c) for c in cids)
            if expected_idx is not None and found == expected_idx:
                rec["classification"] = AUDIT_READY
            elif found == expected_codes:
                rec["classification"] = AUDIT_LEGACY_CODES
            else:
                rec["classification"] = AUDIT_MISMATCH
            rec["label_class_ids"] = found
        records.append(rec)

    summary = {}
    for r in records:
        summary[r["classification"]] = summary.get(r["classification"], 0) + 1
    return {
        "permanent_images": len(records),
        "in_snapshots": sum(1 for r in records if r["in_snapshot"]),
        "summary": summary,
        "images": records,
    }


def backfill_historical_images(db: Session, *, apply: bool = False, include_mismatched: bool = False) -> dict:
    """
    Explicit, idempotent backfill of pre-A1 permanent images. Dry-run unless apply=True.

    Repaired images are regenerated from their DB annotations (never fabricated),
    the previous label is kept as ``<label>.pre_a1.bak``, and the revision is
    finalized on behalf of the image owner. Human-only labels become eligible (A1);
    any AI involvement leaves the image awaiting administrator review (A6.0).
    Existing snapshots are never touched and no snapshot is created here.
    """
    audit = audit_historical_images(db)
    allowed = _BACKFILL_DEFAULT + ((AUDIT_MISMATCH,) if include_mismatched else ())
    candidates = [r["image_id"] for r in audit["images"] if r["classification"] in allowed]
    skipped = [
        {"image_id": r["image_id"], "classification": r["classification"]}
        for r in audit["images"]
        if r["classification"] not in allowed and r["classification"] != AUDIT_ELIGIBLE
    ]
    report = {
        "dry_run": not apply,
        "candidates": candidates,
        "skipped": skipped,
        "already_eligible": audit["summary"].get(AUDIT_ELIGIBLE, 0),
        "finalized": [],
        "failed": [],
    }
    if not apply:
        return report

    for image_id in candidates:
        try:
            result = finalize_image_labeling(
                db, image_id, preserve_previous_label_as=PRE_A1_LABEL_SUFFIX, reconcile=False,
            )
            report["finalized"].append({"image_id": image_id, "training_sequence": result["training_sequence"],
                                        "awaiting_review": result["training_sequence"] is None})
        except LabelingFinalizationError as exc:
            report["failed"].append({"image_id": image_id, "reason": exc.reason})
    logger.info(
        "HISTORICAL_BACKFILL | finalized=%s | failed=%s | skipped=%s",
        len(report["finalized"]), len(report["failed"]), len(skipped),
    )
    return report
