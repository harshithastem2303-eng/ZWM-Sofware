"""
Prediction feedback collection and administrator review (ZWM v1.1.0, Block A6.2).

Rules (all enforced here; the lifecycle and independence rules are also enforced by
PostgreSQL triggers, see app.models.feedback):
  * feedback can be submitted for a prediction the caller can see under the A6.1 rules
    (its requester, or any administrator); otherwise the prediction is "not found";
  * failed predictions cannot receive feedback (there is no result to correct);
  * per type: which detection it targets, whether a suggested class and/or geometry is
    required, optional or forbidden (TYPE_RULES);
  * suggested classes must be existing, active categories; geometry is in original
    image pixel space (the space A6.1 detections are recorded in) and must lie inside
    the image when its size can be read;
  * duplicate rule: one pending or approved report per user, prediction, type and
    target; a rejected report may be resubmitted;
  * decisions: administrators only, never the submitter, exactly one per feedback;
    repeating the same decision is an idempotent no-op, a different one is a conflict.
Nothing here writes to prediction records, annotations, label files, images or
training eligibility.
"""
import math
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.feedback import (
    DECISIONS,
    FEEDBACK_FALSE_DETECTION,
    FEEDBACK_INCORRECT_CLASS,
    FEEDBACK_INCORRECT_GEOMETRY,
    FEEDBACK_MISSED_OBJECT,
    FEEDBACK_OTHER,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    TARGET_PREDICTION,
    FeedbackDecision,
    PredictionFeedback,
    detection_target,
)
from app.models.prediction import STATUS_FAILED, PredictionRecord

MAX_PAGE = 200
MAX_TEXT = 2000
MAX_POLYGON_POINTS = 500
MAX_COORDINATE = 100_000          # sanity bound when the image size is unknown

REQUIRED, OPTIONAL, FORBIDDEN = "required", "optional", "forbidden"
TYPE_RULES = {
    #                             detection  class      geometry   explanation
    FEEDBACK_INCORRECT_CLASS:    (REQUIRED, REQUIRED, OPTIONAL, OPTIONAL),
    FEEDBACK_INCORRECT_GEOMETRY: (REQUIRED, OPTIONAL, REQUIRED, OPTIONAL),
    FEEDBACK_MISSED_OBJECT:      (FORBIDDEN, REQUIRED, REQUIRED, OPTIONAL),
    FEEDBACK_FALSE_DETECTION:    (REQUIRED, FORBIDDEN, FORBIDDEN, OPTIONAL),
    FEEDBACK_OTHER:              (OPTIONAL, OPTIONAL, OPTIONAL, REQUIRED),
}


def actor(principal):
    """(id, email, is_admin) of a User or an Admin row (require_admin may return either)."""
    pid = getattr(principal, "user_id", None) or getattr(principal, "admin_id", None)
    email = getattr(principal, "email", None) or getattr(principal, "admin_email", None)
    is_admin = getattr(principal, "role", None) == "admin" or hasattr(principal, "admin_id")
    return pid, email, is_admin


def _bad(detail: str, code: int = status.HTTP_422_UNPROCESSABLE_ENTITY) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _clean_text(value: Optional[str], field: str, required: bool, min_len: int = 3) -> Optional[str]:
    text = (value or "").strip()
    if not text:
        if required:
            raise _bad(f"'{field}' is required for this feedback.")
        return None
    if len(text) < min_len:
        raise _bad(f"'{field}' must be at least {min_len} characters.")
    if len(text) > MAX_TEXT:
        raise _bad(f"'{field}' must be at most {MAX_TEXT} characters.")
    if any(ord(c) < 32 and c not in "\n\t" for c in text):
        raise _bad(f"'{field}' contains control characters.")
    return text


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def _number(v, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise _bad(f"{what} must be a number.")
    f = float(v)
    if not math.isfinite(f):
        raise _bad(f"{what} must be finite.")
    return f


def _image_size(db: Session, image_id: Optional[str]):
    """(width, height) of the prediction's image when it can be read, else None."""
    if not image_id:
        return None
    from app.models.image import Image
    img = db.query(Image).filter(Image.image_id == image_id).first()
    path = img and (img.permanent_s3_path or img.temp_s3_path)
    if not path or not os.path.isfile(path):
        return None
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            return im.size
    except Exception:
        return None


def validate_geometry(geometry, size=None) -> dict:
    """
    {"type": "bbox", "bbox": [x1, y1, x2, y2]} or
    {"type": "polygon", "points": [{"x":..,"y":..}, ...]} in original image pixels.
    Polygon points follow the existing annotation rules (annotation_service), plus
    finite values, a bounded point count, non-zero area and the image bounds.
    """
    if not isinstance(geometry, dict):
        raise _bad("suggested_geometry must be an object.")
    max_x, max_y = (size if size else (MAX_COORDINATE, MAX_COORDINATE))

    def in_bounds(x, y, i):
        if x < 0 or y < 0 or x > max_x or y > max_y:
            raise _bad(f"Point {i} lies outside the image ({max_x}x{max_y}).")

    kind = geometry.get("type")
    if kind == "bbox":
        box = geometry.get("bbox")
        if not isinstance(box, list) or len(box) != 4:
            raise _bad("A bbox must be [x1, y1, x2, y2].")
        x1, y1, x2, y2 = (_number(v, "bbox value") for v in box)
        in_bounds(x1, y1, 0)
        in_bounds(x2, y2, 1)
        if x2 <= x1 or y2 <= y1:
            raise _bad("A bbox needs x2 > x1 and y2 > y1.")
        return {"type": "bbox", "bbox": [x1, y1, x2, y2]}
    if kind == "polygon":
        from app.services.annotation_service import validate_label_data
        points = geometry.get("points")
        if isinstance(points, list) and len(points) > MAX_POLYGON_POINTS:
            raise _bad(f"A polygon may have at most {MAX_POLYGON_POINTS} points.")
        if isinstance(points, list):
            for i, p in enumerate(points):
                if isinstance(p, dict):
                    _number(p.get("x"), f"Point {i} x")
                    _number(p.get("y"), f"Point {i} y")
        pts = validate_label_data("polygon", {"points": points})["points"]
        for i, p in enumerate(pts):
            in_bounds(p["x"], p["y"], i)
        area = abs(sum(a["x"] * b["y"] - b["x"] * a["y"] for a, b in zip(pts, pts[1:] + pts[:1]))) / 2
        if area < 1:
            raise _bad("A polygon must enclose a non-zero area.")
        return {"type": "polygon", "points": pts}
    raise _bad("suggested_geometry.type must be 'bbox' or 'polygon'.")


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------

def visible_prediction(db: Session, user, prediction_id: str) -> PredictionRecord:
    """The A6.1 visibility rule: requester or administrator, otherwise 404."""
    uid, _, is_admin = actor(user)
    rec = db.query(PredictionRecord).filter(PredictionRecord.prediction_id == prediction_id).first()
    if rec is None or (not is_admin and rec.requested_by != uid):
        raise _bad("Prediction not found", status.HTTP_404_NOT_FOUND)
    return rec


def submit_feedback(db: Session, user, prediction_id: str, *, feedback_type: str,
                    detection_index: Optional[int] = None, explanation: Optional[str] = None,
                    suggested_category_id: Optional[int] = None, suggested_geometry=None) -> PredictionFeedback:
    from app.services.prediction_service import environment_label

    rec = visible_prediction(db, user, prediction_id)
    uid, _, is_admin = actor(user)
    if rec.status == STATUS_FAILED:
        raise _bad("Feedback cannot be submitted for a failed prediction.", status.HTTP_409_CONFLICT)
    if feedback_type not in TYPE_RULES:
        raise _bad(f"Unsupported feedback type '{feedback_type}'.")
    det_rule, cls_rule, geo_rule, text_rule = TYPE_RULES[feedback_type]

    detections = rec.detections or []
    original = None
    if detection_index is None:
        if det_rule == REQUIRED:
            raise _bad("'detection_index' is required for this feedback type.")
    else:
        if det_rule == FORBIDDEN:
            raise _bad("'detection_index' is not allowed for this feedback type.")
        if isinstance(detection_index, bool) or not 0 <= detection_index < len(detections):
            raise _bad(f"'detection_index' must refer to one of the prediction's {len(detections)} detection(s).")
        original = detections[detection_index]

    category = None
    if suggested_category_id is None:
        if cls_rule == REQUIRED:
            raise _bad("'suggested_category_id' is required for this feedback type.")
    else:
        if cls_rule == FORBIDDEN:
            raise _bad("A suggested class is not allowed for this feedback type.")
        category = db.query(Category).filter(Category.category_id == suggested_category_id).first()
        if category is None:
            raise _bad(f"Category ID {suggested_category_id} not found.")
        if not category.is_active:
            raise _bad(f"Category '{category.class_name}' is currently inactive.")
        if (feedback_type == FEEDBACK_INCORRECT_CLASS and original is not None
                and str(original.get("label") or "").strip().lower() == category.class_name.strip().lower()):
            raise _bad("The suggested class is the class that was predicted.")

    geometry = None
    if suggested_geometry is None:
        if geo_rule == REQUIRED:
            raise _bad("'suggested_geometry' is required for this feedback type.")
    else:
        if geo_rule == FORBIDDEN:
            raise _bad("A suggested geometry is not allowed for this feedback type.")
        geometry = validate_geometry(suggested_geometry, _image_size(db, rec.image_id))

    text = _clean_text(explanation, "explanation", text_rule == REQUIRED)
    target = detection_target(detection_index) if detection_index is not None else TARGET_PREDICTION

    duplicate = (db.query(PredictionFeedback.feedback_id)
                 .filter(PredictionFeedback.prediction_id == rec.prediction_id,
                         PredictionFeedback.submitted_by == uid,
                         PredictionFeedback.feedback_type == feedback_type,
                         PredictionFeedback.target == target,
                         PredictionFeedback.status.in_((STATUS_PENDING, STATUS_APPROVED)))
                 .first())
    if duplicate is not None:
        raise _duplicate(duplicate[0])

    fb = PredictionFeedback(
        prediction_id=rec.prediction_id, submitted_by=uid, submitter_role="admin" if is_admin else "user",
        environment=environment_label(), feedback_type=feedback_type, target=target,
        detection_index=detection_index, explanation=text,
        suggested_category_id=category.category_id if category else None,
        suggested_class_name=category.class_name if category else None,
        suggested_yolo_class_index=category.yolo_class_index if category else None,
        suggested_geometry=geometry, image_id=rec.image_id, prediction_source=rec.source,
        model_kind=rec.model_kind, model_attribution=rec.attribution, model_sha256=rec.model_sha256,
        model_version_id=rec.model_version_id, deployment_id=rec.deployment_id,
        original_detection=original, status=STATUS_PENDING,
    )
    db.add(fb)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()                       # a concurrent identical submission won the unique index
        raise _duplicate(None)
    db.refresh(fb)
    return fb


def _duplicate(feedback_id: Optional[str]) -> HTTPException:
    detail = "You already have a pending or approved report of this type for this prediction target."
    if feedback_id:
        detail += f" Existing feedback: {feedback_id}."
    return _bad(detail, status.HTTP_409_CONFLICT)


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

def decide(db: Session, reviewer, feedback_id: str, decision: str, reason: Optional[str]):
    """
    Record the single decision for a pending feedback. Returns (decision_row, replayed):
    replayed=True when the same decision already existed (idempotent; nothing written).
    """
    if decision not in DECISIONS:
        raise _bad("Decision must be 'approved' or 'rejected'.")
    fb = db.query(PredictionFeedback).filter(PredictionFeedback.feedback_id == feedback_id).first()
    if fb is None:
        raise _bad("Feedback not found", status.HTTP_404_NOT_FOUND)
    reviewer_id, reviewer_email, _ = actor(reviewer)
    if _same_person(db, fb.submitted_by, reviewer_id, reviewer_email):
        raise _bad("Feedback must be reviewed by an administrator other than its submitter.",
                   status.HTTP_403_FORBIDDEN)

    existing = _decision_of(db, feedback_id)
    if existing is not None:
        return _replay_or_conflict(existing, decision)

    reason = _clean_text(reason, "reason", decision == STATUS_REJECTED)
    row = FeedbackDecision(feedback_id=feedback_id, decision=decision, reviewer_id=reviewer_id,
                           reviewer_email=reviewer_email, reason=reason,
                           previous_status=STATUS_PENDING)
    try:
        db.add(row)
        db.flush()
        moved = db.execute(update(PredictionFeedback.__table__)
                           .where(PredictionFeedback.__table__.c.feedback_id == feedback_id)
                           .where(PredictionFeedback.__table__.c.status == STATUS_PENDING)
                           .values(status=decision)).rowcount
        if moved != 1:
            raise IntegrityError("feedback status transition lost a race", None, None)
        db.commit()
    except (IntegrityError, DBAPIError):
        # a concurrent decision committed first (unique decision / PostgreSQL guard)
        db.rollback()
        existing = _decision_of(db, feedback_id)
        if existing is None:
            raise _bad("Feedback decision could not be recorded.", status.HTTP_409_CONFLICT)
        return _replay_or_conflict(existing, decision)
    db.refresh(row)
    return row, False


def _same_person(db: Session, submitted_by: str, reviewer_id: Optional[str], reviewer_email: Optional[str]) -> bool:
    """An administrator account and its user account are the same person (id or e-mail)."""
    if submitted_by == reviewer_id:
        return True
    if not reviewer_email:
        return False
    from app.models.user import User
    submitter = db.query(User).filter(User.user_id == submitted_by).first()
    return bool(submitter and (submitter.email or "").strip().lower() == reviewer_email.strip().lower())


def _decision_of(db: Session, feedback_id: str) -> Optional[FeedbackDecision]:
    return db.query(FeedbackDecision).filter(FeedbackDecision.feedback_id == feedback_id).first()


def _replay_or_conflict(existing: FeedbackDecision, decision: str):
    if existing.decision == decision:
        return existing, True
    raise _bad(f"Feedback has already been {existing.decision}; decisions cannot be changed.",
               status.HTTP_409_CONFLICT)


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------

def _iso(dt):
    return dt.isoformat() if dt else None


def decision_dict(d: Optional[FeedbackDecision], admin: bool) -> Optional[dict]:
    if d is None:
        return None
    out = {"decision_id": d.decision_id, "decision": d.decision, "reason": d.reason,
           "previous_status": d.previous_status, "decided_at": _iso(d.decided_at)}
    if admin:
        out.update(reviewer_id=d.reviewer_id, reviewer_email=d.reviewer_email)
    return out


def to_dict(fb: PredictionFeedback, decision: Optional[FeedbackDecision], admin: bool,
            confidence_is_model_score: Optional[bool] = None) -> dict:
    out = {
        "feedback_id": fb.feedback_id, "prediction_id": fb.prediction_id, "status": fb.status,
        "feedback_type": fb.feedback_type, "target": fb.target, "detection_index": fb.detection_index,
        "explanation": fb.explanation, "submitted_at": _iso(fb.submitted_at),
        "suggested_correction": {"category_id": fb.suggested_category_id, "class_name": fb.suggested_class_name,
                                 "yolo_class_index": fb.suggested_yolo_class_index,
                                 "geometry": fb.suggested_geometry},
        "prediction_reference": {"image_id": fb.image_id, "source": fb.prediction_source,
                                 "model_kind": fb.model_kind, "attribution": fb.model_attribution,
                                 "model_sha256": fb.model_sha256, "model_version_id": fb.model_version_id,
                                 "deployment_id": fb.deployment_id,
                                 "confidence_is_model_score": confidence_is_model_score,
                                 "original_detection": fb.original_detection},
        "decision": decision_dict(decision, admin),
        "decision_history": [decision_dict(decision, admin)] if decision else [],
    }
    if admin:
        out.update(submitted_by=fb.submitted_by, submitter_role=fb.submitter_role, environment=fb.environment)
    return out


def list_feedback(db: Session, *, admin: bool, submitted_by: Optional[str] = None,
                  status_: Optional[str] = None, feedback_type: Optional[str] = None,
                  prediction_id: Optional[str] = None, image_id: Optional[str] = None,
                  submitted_from: Optional[datetime] = None, submitted_to: Optional[datetime] = None,
                  oldest_first: bool = False, limit: int = 50, offset: int = 0) -> dict:
    q = (db.query(PredictionFeedback, FeedbackDecision, PredictionRecord.confidence_is_model_score)
         .join(PredictionRecord, PredictionRecord.prediction_id == PredictionFeedback.prediction_id)
         .outerjoin(FeedbackDecision, FeedbackDecision.feedback_id == PredictionFeedback.feedback_id))
    if submitted_by is not None:
        q = q.filter(PredictionFeedback.submitted_by == submitted_by)
    if status_:
        q = q.filter(PredictionFeedback.status == status_)
    if feedback_type:
        q = q.filter(PredictionFeedback.feedback_type == feedback_type)
    if prediction_id:
        q = q.filter(PredictionFeedback.prediction_id == prediction_id)
    if image_id:
        q = q.filter(PredictionFeedback.image_id == image_id)
    submitted_from, submitted_to = (d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d
                                    for d in (submitted_from, submitted_to))
    if submitted_from is not None:
        q = q.filter(PredictionFeedback.submitted_at >= submitted_from)
    if submitted_to is not None:
        q = q.filter(PredictionFeedback.submitted_at <= submitted_to)
    total = q.count()
    when = PredictionFeedback.submitted_at.asc() if oldest_first else PredictionFeedback.submitted_at.desc()
    rows = q.order_by(when, PredictionFeedback.feedback_id).offset(offset).limit(min(limit, MAX_PAGE)).all()
    return {"items": [to_dict(fb, d, admin, cms) for fb, d, cms in rows],
            "total": total, "limit": limit, "offset": offset}


def get_feedback(db: Session, user, feedback_id: str) -> dict:
    """Submitter or administrator; anyone else gets 404 (existence is not revealed)."""
    fb = db.query(PredictionFeedback).filter(PredictionFeedback.feedback_id == feedback_id).first()
    uid, _, admin = actor(user)
    if fb is None or (not admin and fb.submitted_by != uid):
        raise _bad("Feedback not found", status.HTTP_404_NOT_FOUND)
    rec = db.query(PredictionRecord).filter(PredictionRecord.prediction_id == fb.prediction_id).first()
    data = to_dict(fb, _decision_of(db, feedback_id), admin, rec.confidence_is_model_score if rec else None)
    if admin and rec is not None:
        from app.services.prediction_service import to_dict as prediction_dict
        data["prediction"] = prediction_dict(rec, include_requester=True)
    return data
