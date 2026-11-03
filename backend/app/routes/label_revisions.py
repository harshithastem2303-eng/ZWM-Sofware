"""
Label revision routes  —  /api/label-revisions  (ZWM v1.1.0, Block A6.3)

Image owner or administrator (others get 404):
GET    /image/{image_id}                 Revision history + current revision indicator
GET    /image/{image_id}/current         The current (active) revision, with contents
POST   /image/{image_id}/capture         Record the current annotations as a revision
GET    /{revision_id}                    One immutable revision: contents, events,
                                         comparison with its parent, source feedback

Administrators:
GET    /review-queue                     Revisions by status / image / feedback / source
GET    /admin/image/{image_id}           History of any image (administrator view)
GET    /admin/revision/{revision_id}     Any revision (administrator view)
POST   /from-feedback/{feedback_id}      Draft revision from an approved feedback (idempotent)
POST   /{revision_id}/restore            Draft revision restoring an earlier state
POST   /{revision_id}/submit             draft -> submitted
POST   /{revision_id}/approve            submitted -> approved   (independent reviewer)
POST   /{revision_id}/reject             submitted -> rejected   (reason required)
POST   /{revision_id}/activate           Make an approved revision the image's labels

Nothing here trains, activates a model or writes to a frozen snapshot.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user, require_admin
from app.models.user import User
from app.schemas.schemas import LabelRevisionFromFeedback, LabelRevisionReason
from app.services import label_revision_service as lrs
from app.services.feedback_service import actor

router = APIRouter()


def _admin(principal) -> bool:
    return actor(principal)[2]


def _read(db: Session, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    finally:
        db.rollback()                                   # read-only


def _created(db, rev, replayed, principal):
    """201 for a new revision, 200 for an idempotent replay of an existing one."""
    body = {**lrs.revision_dict(db, rev, _admin(principal), detail=True), "idempotent_replay": replayed}
    return JSONResponse(status_code=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
                        content=jsonable_encoder(body))


@router.get("/review-queue")
def review_queue(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    image_id: Optional[str] = None,
    feedback_id: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _read(db, lrs.review_queue, db, status_=status_filter, image_id=image_id, feedback_id=feedback_id,
                 source=source, limit=limit, offset=offset)


@router.get("/admin/image/{image_id}")
def admin_image_revisions(image_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _read(db, lrs.image_revisions, db, admin, image_id)


@router.get("/admin/revision/{revision_id}")
def admin_get_revision(revision_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    def read():
        return lrs.revision_dict(db, lrs.accessible_revision(db, admin, revision_id), True, detail=True)
    return _read(db, read)


@router.get("/image/{image_id}")
def image_revisions(image_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _read(db, lrs.image_revisions, db, current_user, image_id)


@router.get("/image/{image_id}/current")
def current_revision(image_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _read(db, lrs.current_revision, db, current_user, image_id)


@router.post("/image/{image_id}/capture")
def capture(
    image_id: str,
    payload: Optional[LabelRevisionReason] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rev, replayed = lrs.capture(db, current_user, image_id, payload.reason if payload else None)
    return _created(db, rev, replayed, current_user)


@router.post("/from-feedback/{feedback_id}")
def from_feedback(
    feedback_id: str,
    payload: LabelRevisionFromFeedback,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rev, replayed = lrs.create_from_feedback(db, admin, feedback_id, target_object_key=payload.target_object_key,
                                             category_id=payload.category_id, reason=payload.reason)
    return _created(db, rev, replayed, admin)


@router.get("/{revision_id}")
def get_revision(revision_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    def read():
        rev = lrs.accessible_revision(db, current_user, revision_id)
        return lrs.revision_dict(db, rev, _admin(current_user), detail=True)
    return _read(db, read)


@router.post("/{revision_id}/restore")
def restore(revision_id: str, payload: LabelRevisionReason, admin: User = Depends(require_admin),
            db: Session = Depends(get_db)):
    rev, replayed = lrs.restore(db, admin, revision_id, payload.reason)
    return _created(db, rev, replayed, admin)


@router.post("/{revision_id}/submit")
def submit(revision_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rev, replayed = lrs.submit(db, admin, revision_id)
    return {**lrs.revision_dict(db, rev, True, detail=True), "idempotent_replay": replayed}


def _decide(db, admin, revision_id, decision, reason):
    _, replayed = lrs.decide(db, admin, revision_id, decision, reason)
    rev = lrs.accessible_revision(db, admin, revision_id)
    return {**lrs.revision_dict(db, rev, True, detail=True), "idempotent_replay": replayed}


@router.post("/{revision_id}/approve")
def approve(revision_id: str, payload: Optional[LabelRevisionReason] = None, admin: User = Depends(require_admin),
            db: Session = Depends(get_db)):
    return _decide(db, admin, revision_id, "approved", payload.reason if payload else None)


@router.post("/{revision_id}/reject")
def reject(revision_id: str, payload: LabelRevisionReason, admin: User = Depends(require_admin),
           db: Session = Depends(get_db)):
    return _decide(db, admin, revision_id, "rejected", payload.reason)


@router.post("/{revision_id}/activate")
def activate(revision_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return lrs.activate(db, admin, revision_id)
