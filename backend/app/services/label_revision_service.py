"""
Immutable label revisions and governed feedback corrections (ZWM v1.1.0, Block A6.3).

Workflow
--------
1. ``capture``: record the image's current annotation rows as a ``human_annotation``
   revision (status "recorded") and point the image's head at it. Nothing else changes.
2. ``create_from_feedback``: an administrator turns ONE A6.2 feedback with an approved
   decision into a ``draft`` revision: a complete copy of the parent (the head, captured
   first when missing or out of date) with the correction applied. The feedback's
   prediction must still exist and be linked to the same image; the class and geometry
   are re-validated against today's categories and image bounds. Each feedback can be
   applied once (unique index; a repeat returns the existing revision).
3. ``submit`` -> ``decide`` (approve / reject): an administrator who is neither the
   revision's creator, the feedback submitter, the image owner nor an author of any
   object in it. One decision per revision; repeats are idempotent, changes conflict.
4. ``activate`` (approved revisions only, once): refused for training-eligible or
   snapshotted images (their labels are frozen). Re-verifies hashes and contents,
   requires the head to still be the revision's parent and the annotation rows to still
   match it, then -- in one transaction -- rewrites the mutable annotation rows to the
   revision and moves the head. The label file is then rebuilt through the existing
   A6.0 finalize (atomic install, rollback on failure) with user confirmation disabled:
   only an independent A6.0 administrator review of exactly that label can make the
   image training eligible. No training is triggered; no snapshot is touched.

Earlier revisions, prediction records, feedback and decisions are never modified.
"""
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import exists, func, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.annotation import Annotation
from app.models.category import Category
from app.models.feedback import (
    FEEDBACK_FALSE_DETECTION,
    FEEDBACK_INCORRECT_CLASS,
    FEEDBACK_INCORRECT_GEOMETRY,
    FEEDBACK_MISSED_OBJECT,
    STATUS_APPROVED as FEEDBACK_APPROVED,
    FeedbackDecision,
    PredictionFeedback,
)
from app.models.image import Image
from app.models.label_revision import (
    EVENT_ACTIVATED,
    EVENT_APPROVED,
    EVENT_CREATED,
    EVENT_REJECTED,
    EVENT_SUBMITTED,
    SOURCE_ADMIN,
    SOURCE_FEEDBACK,
    SOURCE_HUMAN,
    STATUS_APPROVED,
    STATUS_DRAFT,
    STATUS_RECORDED,
    STATUS_REJECTED,
    STATUS_SUBMITTED,
    LabelRevision,
    LabelRevisionEvent,
    LabelRevisionHead,
)
from app.models.prediction import PredictionRecord
from app.models.user import User
from app.services import training_dataset_service as tds
from app.services.feedback_service import _bad, _clean_text, _image_size, actor, validate_geometry

logger = logging.getLogger(__name__)

MAX_PAGE = 200
MAX_INSTALLED_LABEL_BYTES = 1 << 20
DEFAULT_SIZE = (800, 600)            # same fallback as the YOLO label generator


# ---------------------------------------------------------------------------
# Canonical contents and hashes
# ---------------------------------------------------------------------------

def _sha(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _canon(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def class_map_sha256(class_map) -> str:
    """Same identity formula as the A6.1 prediction records."""
    return hashlib.sha256(json.dumps(class_map, sort_keys=True, default=str).encode()).hexdigest()


def objects_fingerprint(objects: list) -> str:
    """The A6.0 annotation fingerprint the annotation rows have when they equal ``objects``."""
    rows = sorted(objects, key=lambda o: o["key"])
    canon = [[o["key"], o["category_id"], o["annotation_type"], o["label_data"], bool(o["ai_generated"]),
              o["annotated_by"]] for o in rows]
    return _sha(_canon(canon))


def content_sha256(contents: dict) -> str:
    return _sha(_canon({"image": contents["image"],
                        "objects": sorted(contents["objects"], key=lambda o: o["key"])}))


def label_text(contents: dict) -> str:
    """Canonical YOLO label (objects in key order) derived only from the contents."""
    from app.services.annotation_converter import annotation_to_yolo_line
    w, h = contents["image"]["width"], contents["image"]["height"]
    lines = []
    for o in sorted(contents["objects"], key=lambda o: o["key"]):
        if o.get("yolo_class_index") is None or not o.get("annotation_type") or not o.get("label_data"):
            continue
        line = annotation_to_yolo_line(o["annotation_type"], o["label_data"], w, h, o["yolo_class_index"])
        if line:
            lines.append(line)
    return "\n".join(lines) + ("\n" if lines else "")


def _class_refs(db: Session, category_id: Optional[int]) -> tuple:
    cat = db.query(Category).filter(Category.category_id == category_id).first() if category_id else None
    return (cat.class_name, cat.yolo_class_index) if cat else (None, None)


def _object(db: Session, image: Image, *, key, category_id, annotation_type, label_data, ai_generated,
            annotated_by, size) -> dict:
    effective = category_id if category_id is not None else image.selected_category_id
    name, index = _class_refs(db, effective)
    return {"key": key, "category_id": category_id, "effective_category_id": effective, "class_name": name,
            "yolo_class_index": index, "annotation_type": annotation_type, "label_data": label_data,
            "ai_generated": bool(ai_generated), "annotated_by": annotated_by,
            "image_width": size[0], "image_height": size[1]}


def _size(db: Session, image: Image, rows=()) -> tuple:
    size = _image_size(db, image.image_id)
    if size:
        return tuple(size)
    for a in rows:
        if a.image_width and a.image_height:
            return a.image_width, a.image_height
    return DEFAULT_SIZE


def _rows(db: Session, image_id: str) -> list:
    return db.query(Annotation).filter(Annotation.image_id == image_id).all()


def rows_fingerprint(db: Session, image_id: str) -> str:
    return objects_fingerprint([{"key": a.annotation_id, "category_id": a.category_id,
                                 "annotation_type": a.annotation_type, "label_data": a.label_data_json,
                                 "ai_generated": a.ai_generated, "annotated_by": a.annotated_by}
                                for a in _rows(db, image_id)])


def _installed_label(image: Image) -> tuple:
    """(sha256, text) of the image's label file, read only inside the upload root."""
    from app.services.fs_safety import UnsafeFilesystemOperation, assert_within
    path = image.yolo_txt_path
    if not path or not os.path.isfile(path):
        return None, None
    try:
        assert_within(path, settings.UPLOAD_FOLDER, action="read label")
    except UnsafeFilesystemOperation:
        return None, None
    if os.path.getsize(path) > MAX_INSTALLED_LABEL_BYTES:
        return tds.file_sha256(path), None
    with open(path, "rb") as fh:
        data = fh.read()
    return hashlib.sha256(data).hexdigest(), data.decode("utf-8", errors="replace")


def _verify_hashes(rev: LabelRevision) -> Optional[str]:
    """None when the stored hashes still match the stored contents."""
    if content_sha256(rev.contents) != rev.content_sha256:
        return "content_sha256"
    if objects_fingerprint(rev.contents["objects"]) != rev.annotation_fingerprint:
        return "annotation_fingerprint"
    if _sha(rev.label_text) != rev.label_sha256 or label_text(rev.contents) != rev.label_text:
        return "label_sha256"
    if class_map_sha256(rev.class_map) != rev.class_map_sha256:
        return "class_map_sha256"
    return None


# ---------------------------------------------------------------------------
# Status (derived from the append-only events) and head
# ---------------------------------------------------------------------------

def _events(db: Session, revision_id: str) -> dict:
    return {e.event: e for e in db.query(LabelRevisionEvent).filter(LabelRevisionEvent.revision_id == revision_id)}


def status_of(rev: LabelRevision, events: dict) -> str:
    if rev.source == SOURCE_HUMAN:
        return STATUS_RECORDED
    for ev, st in ((EVENT_REJECTED, STATUS_REJECTED), (EVENT_APPROVED, STATUS_APPROVED),
                   (EVENT_SUBMITTED, STATUS_SUBMITTED)):
        if ev in events:
            return st
    return STATUS_DRAFT


def _head(db: Session, image_id: str, lock: bool = False) -> Optional[LabelRevisionHead]:
    q = db.query(LabelRevisionHead).filter(LabelRevisionHead.image_id == image_id)
    if lock:
        q = q.with_for_update().populate_existing()
    return q.first()


def _revision(db: Session, revision_id: Optional[str]) -> Optional[LabelRevision]:
    if not revision_id:
        return None
    return db.query(LabelRevision).filter(LabelRevision.revision_id == revision_id).first()


def _lock_image(db: Session, image_id: str) -> Optional[Image]:
    return (db.query(Image).filter(Image.image_id == image_id)
            .with_for_update(of=Image).populate_existing().first())


def _add_event(db: Session, rev: LabelRevision, event: str, principal, from_status, to_status,
               reason=None, details=None) -> LabelRevisionEvent:
    pid, email, is_admin = actor(principal)
    ev = LabelRevisionEvent(revision_id=rev.revision_id, image_id=rev.image_id, event=event,
                            from_status=from_status, to_status=to_status, actor_id=pid, actor_email=email,
                            actor_role="admin" if is_admin else "user", reason=reason, details=details)
    db.add(ev)
    db.flush()
    return ev


def _move_head(db: Session, image_id: str, rev: LabelRevision, ev: LabelRevisionEvent,
               expected_revision_id: Optional[str]) -> None:
    """Point the image at ``rev``; refuses (IntegrityError) if the head moved meanwhile."""
    now = datetime.now(timezone.utc)
    if expected_revision_id is None:
        if _head(db, image_id) is not None:
            raise IntegrityError("label revision head already exists", None, None)
        db.add(LabelRevisionHead(image_id=image_id, revision_id=rev.revision_id, event_id=ev.event_id,
                                 updated_at=now))
        db.flush()
        return
    moved = db.execute(update(LabelRevisionHead.__table__)
                       .where(LabelRevisionHead.__table__.c.image_id == image_id)
                       .where(LabelRevisionHead.__table__.c.revision_id == expected_revision_id)
                       .values(revision_id=rev.revision_id, event_id=ev.event_id, updated_at=now)).rowcount
    if moved != 1:
        raise IntegrityError("label revision head moved concurrently", None, None)
    db.expire_all()


def _next_number(db: Session, image_id: str) -> int:
    return (db.query(func.max(LabelRevision.revision_number))
            .filter(LabelRevision.image_id == image_id).scalar() or 0) + 1


def _new_revision(db: Session, image: Image, principal, *, source, objects, size, parent, reason,
                  correction=None, feedback=None, decision=None, installed=(None, None)) -> LabelRevision:
    pid, email, is_admin = actor(principal)
    class_map = tds.get_class_map(db)
    contents = {"image": {"width": size[0], "height": size[1]},
                "objects": sorted(objects, key=lambda o: o["key"])}
    text = label_text(contents)
    rev = LabelRevision(
        image_id=image.image_id, revision_number=_next_number(db, image.image_id),
        parent_revision_id=parent.revision_id if parent else None, source=source,
        feedback_id=feedback.feedback_id if feedback else None,
        feedback_decision_id=decision.decision_id if decision else None,
        prediction_id=feedback.prediction_id if feedback else None,
        created_by=pid, created_by_email=email, created_by_role="admin" if is_admin else "user",
        reason=reason, contents=contents, object_count=len(objects), correction=correction,
        class_map=class_map, class_map_sha256=class_map_sha256(class_map),
        content_sha256=content_sha256(contents), annotation_fingerprint=objects_fingerprint(objects),
        label_text=text, label_sha256=_sha(text),
        base_label_sha256=image.label_sha256, base_training_sequence=image.training_sequence,
        base_training_review_id=image.training_review_id, base_label_provenance=image.label_provenance,
        installed_label_sha256=installed[0], installed_label_text=installed[1],
    )
    db.add(rev)
    db.flush()
    return rev


def _capture_locked(db: Session, image: Image, principal, reason: Optional[str]) -> tuple:
    """(head revision, created) -- records the current rows unless the head already matches them."""
    head = _head(db, image.image_id, lock=True)
    current = _revision(db, head.revision_id) if head else None
    fingerprint = rows_fingerprint(db, image.image_id)
    if current is not None and current.annotation_fingerprint == fingerprint:
        return current, False
    rows = _rows(db, image.image_id)
    size = _size(db, image, rows)
    objects = [_object(db, image, key=a.annotation_id, category_id=a.category_id,
                       annotation_type=a.annotation_type, label_data=a.label_data_json,
                       ai_generated=a.ai_generated, annotated_by=a.annotated_by, size=size) for a in rows]
    rev = _new_revision(db, image, principal, source=SOURCE_HUMAN, objects=objects, size=size, parent=current,
                        reason=reason or "Recorded current annotations", installed=_installed_label(image))
    ev = _add_event(db, rev, EVENT_CREATED, principal, None, STATUS_RECORDED, reason=rev.reason,
                    details={"in_sync_with_previous_head": False if current else None})
    _move_head(db, image.image_id, rev, ev, head.revision_id if head else None)
    return rev, True


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------

def accessible_image(db: Session, principal, image_id: str) -> Image:
    """Image owner or administrator; anyone else gets 404 (existence is not revealed)."""
    uid, _, is_admin = actor(principal)
    img = db.query(Image).filter(Image.image_id == image_id).first()
    if img is None or (not is_admin and img.user_id != uid):
        raise _bad("Image not found", status.HTTP_404_NOT_FOUND)
    return img


def accessible_revision(db: Session, principal, revision_id: str) -> LabelRevision:
    rev = _revision(db, revision_id)
    if rev is None:
        raise _bad("Label revision not found", status.HTTP_404_NOT_FOUND)
    try:
        accessible_image(db, principal, rev.image_id)
    except HTTPException:
        _, _, is_admin = actor(principal)
        if not is_admin:                                     # evidence of a deleted image: admins only
            raise _bad("Label revision not found", status.HTTP_404_NOT_FOUND)
    return rev


def _commit(db: Session, what: str):
    try:
        db.commit()
    except (IntegrityError, DBAPIError) as exc:
        db.rollback()
        logger.info("LABEL_REVISION_CONFLICT | %s | %s", what, type(exc).__name__)
        raise _bad(f"Label revision {what} conflicted with a concurrent change; reload and retry.",
                   status.HTTP_409_CONFLICT)


# ---------------------------------------------------------------------------
# 1. Capture
# ---------------------------------------------------------------------------

def capture(db: Session, principal, image_id: str, reason: Optional[str] = None) -> tuple:
    accessible_image(db, principal, image_id)
    reason = _clean_text(reason, "reason", False)
    image = _lock_image(db, image_id)
    rev, created = _capture_locked(db, image, principal, reason)
    if created:
        _commit(db, "capture")
        logger.info("LABEL_REVISION_RECORDED | image_id=%s | revision=%s | n=%s", image_id, rev.revision_number,
                    rev.object_count)
    else:
        db.rollback()
    return rev, not created


# ---------------------------------------------------------------------------
# 2. Proposals: approved feedback / administrator restore
# ---------------------------------------------------------------------------

def _require_admin(principal):
    if not actor(principal)[2]:
        raise _bad("Administrator privileges required", status.HTTP_403_FORBIDDEN)


def _active_category(db: Session, category_id: int) -> Category:
    cat = db.query(Category).filter(Category.category_id == category_id).first()
    if cat is None:
        raise _bad(f"Category ID {category_id} not found.")
    if not cat.is_active:
        raise _bad(f"Category '{cat.class_name}' is currently inactive.", status.HTTP_409_CONFLICT)
    return cat


def _shape(geometry: dict) -> tuple:
    if geometry["type"] == "bbox":
        x1, y1, x2, y2 = geometry["bbox"]
        return "rectangle", {"points": [{"x": x1, "y": y1}, {"x": x2, "y": y2}]}
    return "polygon", {"points": [{"x": p["x"], "y": p["y"]} for p in geometry["points"]]}


def _detection_geometry(det: Optional[dict]) -> Optional[dict]:
    if not isinstance(det, dict):
        return None
    poly = det.get("polygon")
    if isinstance(poly, list) and len(poly) >= 3:
        return {"type": "polygon", "points": poly}
    if isinstance(det.get("bbox"), list):
        return {"type": "bbox", "bbox": det["bbox"]}
    return None


def _approved_feedback(db: Session, feedback_id: str) -> tuple:
    """(feedback, decision, prediction, image) or HTTP error -- steps 1-5 of the workflow."""
    fb = db.query(PredictionFeedback).filter(PredictionFeedback.feedback_id == feedback_id).first()
    if fb is None:
        raise _bad("Feedback not found", status.HTTP_404_NOT_FOUND)
    decision = db.query(FeedbackDecision).filter(FeedbackDecision.feedback_id == feedback_id).first()
    if fb.status != FEEDBACK_APPROVED or decision is None or decision.decision != FEEDBACK_APPROVED:
        raise _bad(f"Only feedback with an approved administrator decision can be applied (status: {fb.status}).",
                   status.HTTP_409_CONFLICT)
    from app.services.feedback_service import _same_person
    if _same_person(db, fb.submitted_by, decision.reviewer_id, decision.reviewer_email):
        raise _bad("The feedback decision was not an independent review.", status.HTTP_409_CONFLICT)
    rec = db.query(PredictionRecord).filter(PredictionRecord.prediction_id == fb.prediction_id).first()
    if rec is None:
        raise _bad("The feedback's original prediction no longer exists.", status.HTTP_409_CONFLICT)
    if not fb.image_id or not rec.image_id:
        raise _bad("The feedback's prediction has no stored image; a revision cannot be created until a valid "
                   "image association is established.", status.HTTP_409_CONFLICT)
    if fb.image_id != rec.image_id:
        raise _bad("The feedback is not linked to its prediction's image.", status.HTTP_409_CONFLICT)
    image = db.query(Image).filter(Image.image_id == fb.image_id).first()
    if image is None:
        raise _bad("The feedback's image no longer exists.", status.HTTP_409_CONFLICT)
    if db.query(User.user_id).filter(User.user_id == fb.submitted_by).first() is None:
        raise _bad("The feedback submitter is not a user account; the correction has no author.",
                   status.HTTP_409_CONFLICT)
    return fb, decision, rec, image


def _apply_feedback(db: Session, image: Image, fb: PredictionFeedback, objects: list, size: tuple,
                    target_key: Optional[str], category_id: Optional[int]) -> tuple:
    """New object list + correction record. Never mutates ``objects``."""
    objects = [dict(o) for o in objects]
    by_key = {o["key"]: o for o in objects}
    if target_key is not None and target_key not in by_key:
        raise _bad("target_object_key is not an object of the current label revision.")
    if category_id is not None and fb.suggested_category_id is not None and category_id != fb.suggested_category_id:
        raise _bad("category_id must match the class suggested in the approved feedback.")
    cat_id = fb.suggested_category_id if fb.suggested_category_id is not None else category_id
    cat = _active_category(db, cat_id) if cat_id is not None else None
    if cat is not None:
        tds.ensure_yolo_class_indices(db)
    author = fb.submitted_by

    def new_object(geometry, ai):
        kind, data = _shape(validate_geometry(geometry, size))
        return _object(db, image, key=str(uuid.uuid4()), category_id=cat.category_id, annotation_type=kind,
                       label_data=data, ai_generated=ai, annotated_by=author, size=size)

    t = fb.feedback_type
    action, geometry_from = None, None
    if t in (FEEDBACK_INCORRECT_CLASS, FEEDBACK_INCORRECT_GEOMETRY):
        if t == FEEDBACK_INCORRECT_GEOMETRY and fb.suggested_geometry is None:
            raise _bad("The feedback has no suggested geometry.", status.HTTP_409_CONFLICT)
        geometry = fb.suggested_geometry or _detection_geometry(fb.original_detection)
        geometry_from = "feedback" if fb.suggested_geometry else "prediction"
        if target_key is None:
            if cat is None:
                raise _bad("category_id is required to add this object (the feedback suggests no class).")
            if geometry is None:
                raise _bad("The predicted detection has no usable geometry.", status.HTTP_409_CONFLICT)
            obj = new_object(geometry, ai=geometry_from == "prediction")
            objects.append(obj)
            action = {"action": "add", "object_key": obj["key"]}
        else:
            o = by_key[target_key]
            if cat is not None:
                o.update(category_id=cat.category_id, effective_category_id=cat.category_id,
                         class_name=cat.class_name, yolo_class_index=cat.yolo_class_index)
            if fb.suggested_geometry is not None:
                kind, data = _shape(validate_geometry(fb.suggested_geometry, size))
                o.update(annotation_type=kind, label_data=data, ai_generated=False)
            else:
                geometry_from = "unchanged"
            o["annotated_by"] = author
            action = {"action": "modify", "object_key": target_key}
    elif t == FEEDBACK_MISSED_OBJECT:
        if target_key is not None:
            raise _bad("target_object_key is not allowed for a missed object (it adds an object).")
        obj = new_object(fb.suggested_geometry, ai=False)
        objects.append(obj)
        geometry_from = "feedback"
        action = {"action": "add", "object_key": obj["key"]}
    elif t == FEEDBACK_FALSE_DETECTION:
        if target_key is None:
            raise _bad("target_object_key is required: choose the labelled object the false detection produced.")
        objects = [o for o in objects if o["key"] != target_key]
        action = {"action": "remove", "object_key": target_key}
    else:
        raise _bad("This feedback type carries no structured correction and cannot be applied automatically.",
                   status.HTTP_409_CONFLICT)
    correction = {**action, "feedback_type": t, "geometry_from": geometry_from,
                  "category_id": cat.category_id if cat else None,
                  "request": {"target_object_key": target_key, "category_id": category_id}}
    return objects, correction


def _same_request(rev: LabelRevision, request: dict) -> bool:
    return (rev.correction or {}).get("request") == request


def create_from_feedback(db: Session, principal, feedback_id: str, *, target_object_key: Optional[str] = None,
                         category_id: Optional[int] = None, reason: Optional[str] = None) -> tuple:
    """(revision, replayed). Creates a draft revision from approved feedback."""
    _require_admin(principal)
    request = {"target_object_key": target_object_key, "category_id": category_id}

    def replay(existing):
        if not _same_request(existing, request):
            raise _bad(f"Feedback has already been applied as label revision {existing.revision_id}.",
                       status.HTTP_409_CONFLICT)
        return existing, True

    existing = db.query(LabelRevision).filter(LabelRevision.feedback_id == feedback_id).first()
    if existing is not None:
        return replay(existing)
    fb, decision, rec, image = _approved_feedback(db, feedback_id)
    reason = _clean_text(reason, "reason", True)

    image = _lock_image(db, image.image_id)
    existing = db.query(LabelRevision).filter(LabelRevision.feedback_id == feedback_id).first()
    if existing is not None:                                   # applied while we waited for the lock
        db.rollback()
        return replay(existing)
    parent, _ = _capture_locked(db, image, principal, "Recorded before applying feedback")
    size = (parent.contents["image"]["width"], parent.contents["image"]["height"])
    objects, correction = _apply_feedback(db, image, fb, parent.contents["objects"], size,
                                          target_object_key, category_id)
    if not objects:
        db.rollback()
        raise _bad("The correction would leave the image without any labelled object.", status.HTTP_409_CONFLICT)
    if objects_fingerprint(objects) == parent.annotation_fingerprint:
        db.rollback()
        raise _bad("The correction does not change the current label.", status.HTTP_409_CONFLICT)
    rev = _new_revision(db, image, principal, source=SOURCE_FEEDBACK, objects=objects, size=size, parent=parent,
                        reason=reason, correction=correction, feedback=fb, decision=decision)
    _add_event(db, rev, EVENT_CREATED, principal, None, STATUS_DRAFT, reason=reason,
               details={"feedback_id": fb.feedback_id, "feedback_decision_id": decision.decision_id,
                        "prediction_id": rec.prediction_id})
    try:
        db.commit()
    except (IntegrityError, DBAPIError):
        db.rollback()
        existing = db.query(LabelRevision).filter(LabelRevision.feedback_id == feedback_id).first()
        if existing is not None:
            return replay(existing)
        raise _bad("Label revision creation conflicted with a concurrent change; retry.", status.HTTP_409_CONFLICT)
    logger.info("LABEL_REVISION_PROPOSED | image_id=%s | revision=%s | feedback_id=%s | %s",
                image.image_id, rev.revision_number, feedback_id, correction["action"])
    return rev, False


def restore(db: Session, principal, revision_id: str, reason: Optional[str]) -> tuple:
    """(revision, replayed). Draft ``admin_correction`` revision with an earlier revision's contents."""
    _require_admin(principal)
    source = accessible_revision(db, principal, revision_id)
    reason = _clean_text(reason, "reason", True)
    image = _lock_image(db, source.image_id)
    if image is None:
        raise _bad("The revision's image no longer exists.", status.HTTP_409_CONFLICT)
    parent, _ = _capture_locked(db, image, principal, "Recorded before restoring a revision")
    objects = source.contents["objects"]
    if source.annotation_fingerprint == parent.annotation_fingerprint:
        db.rollback()
        raise _bad("The current label already equals that revision.", status.HTTP_409_CONFLICT)
    for rev in (db.query(LabelRevision).filter(LabelRevision.image_id == image.image_id,
                                               LabelRevision.source == SOURCE_ADMIN,
                                               LabelRevision.parent_revision_id == parent.revision_id,
                                               LabelRevision.annotation_fingerprint == source.annotation_fingerprint)):
        if status_of(rev, _events(db, rev.revision_id)) in (STATUS_DRAFT, STATUS_SUBMITTED, STATUS_APPROVED):
            db.rollback()
            return rev, True                                   # same open proposal: idempotent
    size = (source.contents["image"]["width"], source.contents["image"]["height"])
    rev = _new_revision(db, image, principal, source=SOURCE_ADMIN, objects=[dict(o) for o in objects], size=size,
                        parent=parent, reason=reason,
                        correction={"action": "restore", "restored_revision_id": source.revision_id,
                                    "restored_revision_number": source.revision_number})
    _add_event(db, rev, EVENT_CREATED, principal, None, STATUS_DRAFT, reason=reason,
               details={"restored_revision_id": source.revision_id})
    _commit(db, "creation")
    return rev, False


# ---------------------------------------------------------------------------
# 3. Lifecycle
# ---------------------------------------------------------------------------

def submit(db: Session, principal, revision_id: str) -> tuple:
    _require_admin(principal)
    rev = accessible_revision(db, principal, revision_id)
    events = _events(db, revision_id)
    st = status_of(rev, events)
    if st == STATUS_SUBMITTED:
        return rev, True
    if st != STATUS_DRAFT:
        raise _bad(f"Only a draft revision can be submitted (status: {st}).", status.HTTP_409_CONFLICT)
    _add_event(db, rev, EVENT_SUBMITTED, principal, STATUS_DRAFT, STATUS_SUBMITTED)
    try:
        db.commit()
    except (IntegrityError, DBAPIError):
        db.rollback()
        if status_of(rev, _events(db, revision_id)) == STATUS_SUBMITTED:
            return rev, True
        raise _bad("Revision submission conflicted with a concurrent change.", status.HTTP_409_CONFLICT)
    return rev, False


def _not_independent(db: Session, rev: LabelRevision, principal) -> bool:
    pid, email, _ = actor(principal)
    ids = {rev.created_by} | {o.get("annotated_by") for o in rev.contents["objects"]}
    image = db.query(Image).filter(Image.image_id == rev.image_id).first()
    if image is not None:
        ids.add(image.user_id)
    if rev.feedback_id:
        fb = db.query(PredictionFeedback).filter(PredictionFeedback.feedback_id == rev.feedback_id).first()
        if fb is not None:
            ids.add(fb.submitted_by)
    ids.discard(None)
    if pid in ids:
        return True
    if not email:
        return False
    emails = {(e or "").strip().lower() for (e,) in db.query(User.email).filter(User.user_id.in_(ids))}
    if rev.created_by_email:
        emails.add(rev.created_by_email.strip().lower())
    return email.strip().lower() in emails


def decide(db: Session, principal, revision_id: str, decision: str, reason: Optional[str]) -> tuple:
    """(decision event, replayed)."""
    _require_admin(principal)
    if decision not in (STATUS_APPROVED, STATUS_REJECTED):
        raise _bad("Decision must be 'approved' or 'rejected'.")
    rev = accessible_revision(db, principal, revision_id)
    if _not_independent(db, rev, principal):
        raise _bad("A label revision must be reviewed by an administrator who did not create it, request it or "
                   "author its labels.", status.HTTP_403_FORBIDDEN)

    def replay_or_conflict(events):
        prior = events.get(EVENT_APPROVED) or events.get(EVENT_REJECTED)
        if prior.event == decision:
            return prior, True
        raise _bad(f"Revision has already been {prior.event}; decisions cannot be changed.",
                   status.HTTP_409_CONFLICT)

    events = _events(db, revision_id)
    if EVENT_APPROVED in events or EVENT_REJECTED in events:
        return replay_or_conflict(events)
    st = status_of(rev, events)
    if st != STATUS_SUBMITTED:
        raise _bad(f"Only a submitted revision can be reviewed (status: {st}).", status.HTTP_409_CONFLICT)
    reason = _clean_text(reason, "reason", decision == STATUS_REJECTED)
    problem = _verify_hashes(rev)
    if decision == STATUS_APPROVED and problem:
        raise _bad(f"Revision integrity check failed ({problem}).", status.HTTP_409_CONFLICT)
    ev = _add_event(db, rev, decision, principal, STATUS_SUBMITTED, decision, reason=reason)
    try:
        db.commit()
    except (IntegrityError, DBAPIError):
        db.rollback()
        events = _events(db, revision_id)
        if EVENT_APPROVED in events or EVENT_REJECTED in events:
            return replay_or_conflict(events)
        raise _bad("Revision decision could not be recorded.", status.HTTP_409_CONFLICT)
    logger.info("LABEL_REVISION_%s | revision_id=%s", decision.upper(), revision_id)
    return ev, False


def _contents_problem(db: Session, rev: LabelRevision, image: Image) -> Optional[str]:
    from app.services.annotation_converter import shape_to_bbox
    from app.services.annotation_service import validate_annotation_type, validate_label_data
    objects = rev.contents["objects"]
    if not objects:
        return "no_objects"
    size = _image_size(db, image.image_id) or (rev.contents["image"]["width"], rev.contents["image"]["height"])
    authors = {o["annotated_by"] for o in objects}
    known = {u for (u,) in db.query(User.user_id).filter(User.user_id.in_(authors))}
    for o in objects:
        if o["annotated_by"] not in known:
            return f"unknown_author:{o['key']}"
        cid = o["category_id"] if o["category_id"] is not None else image.selected_category_id
        cat = db.query(Category).filter(Category.category_id == cid).first() if cid is not None else None
        if cat is None or not cat.is_active or cat.yolo_class_index is None:
            return f"invalid_or_inactive_category:{o['key']}"
        try:
            kind = validate_annotation_type(o["annotation_type"] or "")
            validate_label_data(kind, o["label_data"])
        except HTTPException:
            return f"invalid_geometry:{o['key']}"
        box = shape_to_bbox(kind, o["label_data"])
        if box is None or box[2] > size[0] or box[3] > size[1] or box[0] < 0 or box[1] < 0:
            return f"invalid_geometry:{o['key']}"
    return None


def _materialize(db: Session, image: Image, rev: LabelRevision) -> dict:
    """Make the annotation rows equal the revision (rows are mutable working state)."""
    rows = {a.annotation_id: a for a in _rows(db, image.image_id)}
    wanted = {o["key"]: o for o in rev.contents["objects"]}
    stats = {"added": 0, "changed": 0, "removed": 0, "unchanged": 0}
    for key, row in rows.items():
        if key not in wanted:
            db.delete(row)
            stats["removed"] += 1
    for key, o in wanted.items():
        fields = dict(category_id=o["category_id"], annotation_type=o["annotation_type"],
                      label_data_json=o["label_data"], ai_generated=bool(o["ai_generated"]),
                      annotated_by=o["annotated_by"], image_width=o.get("image_width"),
                      image_height=o.get("image_height"))
        row = rows.get(key)
        if row is None:
            db.add(Annotation(annotation_id=key, image_id=image.image_id, **fields))
            stats["added"] += 1
        elif any(getattr(row, k) != v for k, v in fields.items() if k not in ("image_width", "image_height")):
            for k, v in fields.items():
                setattr(row, k, v)
            stats["changed"] += 1
        else:
            stats["unchanged"] += 1
    db.flush()
    return stats


def activate(db: Session, principal, revision_id: str) -> dict:
    _require_admin(principal)
    rev = accessible_revision(db, principal, revision_id)
    events = _events(db, revision_id)
    head = _head(db, rev.image_id)
    if EVENT_ACTIVATED in events:
        if head is not None and head.revision_id == revision_id:
            return {**_activation_state(db, rev), "idempotent_replay": True}
        raise _bad("This revision was activated earlier and has since been superseded; restore it as a new "
                   "revision instead.", status.HTTP_409_CONFLICT)
    st = status_of(rev, events)
    if st != STATUS_APPROVED:
        raise _bad(f"Only an approved revision can be activated (status: {st}).", status.HTTP_409_CONFLICT)
    problem = _verify_hashes(rev)
    if problem:
        raise _bad(f"Revision integrity check failed ({problem}).", status.HTTP_409_CONFLICT)

    image = _lock_image(db, rev.image_id)
    if image is None:
        db.rollback()
        raise _bad("The revision's image no longer exists.", status.HTTP_409_CONFLICT)
    if image.training_sequence is not None or tds.is_in_snapshot(db, image.image_id):
        db.rollback()
        raise _bad("The image is training eligible or part of a frozen training snapshot; its labels are locked "
                   "and the revision cannot be activated.", status.HTTP_409_CONFLICT)
    head = _head(db, image.image_id, lock=True)
    if head is None or head.revision_id != rev.parent_revision_id:
        db.rollback()
        raise _bad("The image's current label revision changed since this revision was proposed.",
                   status.HTTP_409_CONFLICT)
    parent = _revision(db, rev.parent_revision_id)
    if rows_fingerprint(db, image.image_id) != parent.annotation_fingerprint:
        db.rollback()
        raise _bad("The image's annotations changed since this revision was proposed.", status.HTTP_409_CONFLICT)
    problem = _contents_problem(db, rev, image)
    if problem:
        db.rollback()
        raise _bad(f"The revision contents are no longer valid ({problem}).", status.HTTP_409_CONFLICT)

    try:
        stats = _materialize(db, image, rev)
        details = {"annotations": stats, "previous_revision_id": parent.revision_id}
        if rev.source == SOURCE_FEEDBACK and image.ai_suggested_at is None:
            # an AI prediction was served for this image: A6.0 review is mandatory
            image.ai_suggested_at = datetime.now(timezone.utc)
            details["ai_suggestion_recorded"] = True
        ev = _add_event(db, rev, EVENT_ACTIVATED, principal, STATUS_APPROVED, STATUS_APPROVED, details=details)
        _move_head(db, image.image_id, rev, ev, parent.revision_id)
        if rows_fingerprint(db, image.image_id) != rev.annotation_fingerprint:
            raise IntegrityError("materialized rows do not match the revision", None, None)
        db.commit()
    except (IntegrityError, DBAPIError) as exc:
        db.rollback()
        logger.info("LABEL_REVISION_ACTIVATION_REFUSED | revision_id=%s | %s", revision_id, type(exc).__name__)
        raise _bad("Activation conflicted with a concurrent change; nothing was changed.", status.HTTP_409_CONFLICT)
    except Exception:
        db.rollback()
        raise
    logger.info("LABEL_REVISION_ACTIVATED | image_id=%s | revision=%s | %s", image.image_id,
                rev.revision_number, stats)

    finalize = {"attempted": False, "finalized": False, "reason": None}
    db.refresh(image)
    if image.status == "permanent":
        finalize["attempted"] = True
        pid, _, _ = actor(principal)
        try:
            tds.finalize_image_labeling(db, image.image_id, finalized_by=pid, allow_user_confirmed=False)
            finalize["finalized"] = True
        except tds.LabelingFinalizationError as exc:
            finalize["reason"] = exc.reason
        except Exception as exc:                                # label file left as it was (finalize rolls back)
            db.rollback()
            logger.error("LABEL_REVISION_FINALIZE_FAILED | revision_id=%s | %s", revision_id, type(exc).__name__)
            finalize["reason"] = "finalize_failed"
    else:
        finalize["reason"] = "image_not_permanent"
    return {**_activation_state(db, rev), "idempotent_replay": False, "finalize": finalize}


def _activation_state(db: Session, rev: LabelRevision) -> dict:
    db.expire_all()
    image = db.query(Image).filter(Image.image_id == rev.image_id).first()
    review = image and tds.label_review_state(db, image)
    return {"revision_id": rev.revision_id, "image_id": rev.image_id, "active": True,
            "label_finalized": bool(review and review["finalized_revision_current"]),
            "label_sha256": image.label_sha256 if image else None,
            "training_eligible": bool(image and image.training_sequence is not None),
            "awaiting_label_review": bool(review and review["finalized_revision_current"]
                                          and image.training_sequence is None)}


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------

def _iso(dt):
    return dt.isoformat() if dt else None


def _event_dict(e: LabelRevisionEvent, admin: bool) -> dict:
    out = {"event_id": e.event_id, "event": e.event, "from_status": e.from_status, "to_status": e.to_status,
           "actor_role": e.actor_role, "reason": e.reason, "details": e.details, "created_at": _iso(e.created_at)}
    if admin:
        out.update(actor_id=e.actor_id, actor_email=e.actor_email)
    return out


def _diff(parent: Optional[LabelRevision], rev: LabelRevision) -> Optional[dict]:
    if parent is None:
        return None
    old = {o["key"]: o for o in parent.contents["objects"]}
    new = {o["key"]: o for o in rev.contents["objects"]}
    fields = ("category_id", "annotation_type", "label_data", "ai_generated", "annotated_by")
    changed = [{"key": k, "before": old[k], "after": new[k]} for k in sorted(old.keys() & new.keys())
               if any(old[k].get(f) != new[k].get(f) for f in fields)]
    return {"parent_revision_id": parent.revision_id, "parent_revision_number": parent.revision_number,
            "added": [new[k] for k in sorted(new.keys() - old.keys())],
            "removed": [old[k] for k in sorted(old.keys() - new.keys())],
            "changed": changed}


def revision_dict(db: Session, rev: LabelRevision, admin: bool, *, detail: bool = False,
                  head: Optional[LabelRevisionHead] = None, events: Optional[dict] = None) -> dict:
    events = _events(db, rev.revision_id) if events is None else events
    head = head if head is not None else _head(db, rev.image_id)
    out = {
        "revision_id": rev.revision_id, "image_id": rev.image_id, "revision_number": rev.revision_number,
        "parent_revision_id": rev.parent_revision_id, "source": rev.source, "status": status_of(rev, events),
        "is_active": bool(head and head.revision_id == rev.revision_id), "activated": EVENT_ACTIVATED in events,
        "feedback_id": rev.feedback_id, "prediction_id": rev.prediction_id,
        "created_by_role": rev.created_by_role, "created_at": _iso(rev.created_at), "reason": rev.reason,
        "object_count": rev.object_count, "correction": rev.correction,
        "hashes": {"content_sha256": rev.content_sha256, "annotation_fingerprint": rev.annotation_fingerprint,
                   "label_sha256": rev.label_sha256, "class_map_sha256": rev.class_map_sha256},
        "base": {"label_sha256": rev.base_label_sha256, "training_sequence": rev.base_training_sequence,
                 "training_review_id": rev.base_training_review_id,
                 "label_provenance": rev.base_label_provenance,
                 "installed_label_sha256": rev.installed_label_sha256},
    }
    if admin:
        out.update(created_by=rev.created_by, created_by_email=rev.created_by_email,
                   feedback_decision_id=rev.feedback_decision_id)
    if detail:
        out.update(contents=rev.contents, class_map=rev.class_map, label_text=rev.label_text,
                   installed_label_text=rev.installed_label_text,
                   integrity_ok=_verify_hashes(rev) is None,
                   events=[_event_dict(e, admin) for e in sorted(events.values(), key=lambda e: (
                       ("created", "submitted", "approved", "rejected", "activated").index(e.event)))],
                   comparison=_diff(_revision(db, rev.parent_revision_id), rev))
        if rev.feedback_id:
            from app.services.feedback_service import get_feedback
            fb = db.query(PredictionFeedback).filter(PredictionFeedback.feedback_id == rev.feedback_id).first()
            if admin:
                out["source_feedback"] = get_feedback(db, _AdminView, rev.feedback_id)
            elif fb is not None:
                out["source_feedback"] = {"feedback_id": fb.feedback_id, "feedback_type": fb.feedback_type,
                                          "status": fb.status, "prediction_id": fb.prediction_id}
    return out


class _AdminView:
    """Principal used to read source feedback with administrator detail."""
    admin_id, admin_email = "label-revision-view", None


def image_revisions(db: Session, principal, image_id: str) -> dict:
    accessible_image(db, principal, image_id)
    _, _, admin = actor(principal)
    head = _head(db, image_id)
    revs = (db.query(LabelRevision).filter(LabelRevision.image_id == image_id)
            .order_by(LabelRevision.revision_number.desc()).all())
    image = db.query(Image).filter(Image.image_id == image_id).first()
    live = [{"key": a.annotation_id, "category_id": a.category_id, "class_name": _class_refs(
                 db, a.category_id if a.category_id is not None else image.selected_category_id)[0],
             "annotation_type": a.annotation_type, "ai_generated": bool(a.ai_generated)}
            for a in sorted(_rows(db, image_id), key=lambda a: a.annotation_id)]
    return {"image_id": image_id, "current": current_state(db, image_id, head),
            "training_locked": image.training_sequence is not None or tds.is_in_snapshot(db, image_id),
            "annotations": live,
            "items": [revision_dict(db, r, admin, head=head) for r in revs], "total": len(revs)}


def current_state(db: Session, image_id: str, head: Optional[LabelRevisionHead] = None) -> dict:
    head = head if head is not None else _head(db, image_id)
    rev = _revision(db, head.revision_id) if head else None
    in_sync = bool(rev and rows_fingerprint(db, image_id) == rev.annotation_fingerprint)
    return {"revision_id": rev.revision_id if rev else None,
            "revision_number": rev.revision_number if rev else None,
            "source": rev.source if rev else None, "since": _iso(head.updated_at) if head else None,
            "in_sync_with_annotations": in_sync}


def current_revision(db: Session, principal, image_id: str) -> dict:
    accessible_image(db, principal, image_id)
    _, _, admin = actor(principal)
    head = _head(db, image_id)
    rev = _revision(db, head.revision_id) if head else None
    return {"image_id": image_id, "current": current_state(db, image_id, head),
            "revision": revision_dict(db, rev, admin, detail=True, head=head) if rev else None}


def review_queue(db: Session, *, status_: Optional[str] = None, image_id: Optional[str] = None,
                 feedback_id: Optional[str] = None, source: Optional[str] = None,
                 limit: int = 50, offset: int = 0) -> dict:
    E = LabelRevisionEvent
    q = db.query(LabelRevision)

    def has(event):
        return exists().where(E.revision_id == LabelRevision.revision_id, E.event == event)

    if status_ == STATUS_RECORDED:
        q = q.filter(LabelRevision.source == SOURCE_HUMAN)
    elif status_ == STATUS_DRAFT:
        q = q.filter(LabelRevision.source != SOURCE_HUMAN, ~has(EVENT_SUBMITTED))
    elif status_ == STATUS_SUBMITTED:
        q = q.filter(has(EVENT_SUBMITTED), ~has(EVENT_APPROVED), ~has(EVENT_REJECTED))
    elif status_ in (STATUS_APPROVED, STATUS_REJECTED):
        q = q.filter(has(status_))
    elif status_ == "active":
        q = q.filter(exists().where(LabelRevisionHead.revision_id == LabelRevision.revision_id))
    elif status_:
        raise _bad("status must be recorded, draft, submitted, approved, rejected or active.")
    if image_id:
        q = q.filter(LabelRevision.image_id == image_id)
    if feedback_id:
        q = q.filter(LabelRevision.feedback_id == feedback_id)
    if source:
        q = q.filter(LabelRevision.source == source)
    total = q.count()
    rows = (q.order_by(LabelRevision.created_at.desc(), LabelRevision.revision_id)
            .offset(offset).limit(min(limit, MAX_PAGE)).all())
    return {"items": [revision_dict(db, r, True) for r in rows], "total": total, "limit": limit, "offset": offset}
