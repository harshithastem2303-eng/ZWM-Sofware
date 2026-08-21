"""
Image Lifecycle Management Routes.

POST /api/lifecycle/images/{image_id}/promote
    – Promote an image from temporary to permanent storage.
    – Requires a valid YOLO TXT to be associated (via annotation or explicit path).
    – Available to image owner or admin.

GET  /api/lifecycle/images/{image_id}/status
    – Return the current lifecycle state of an image.
    – Available to image owner or admin.

POST /api/lifecycle/cleanup
    – Admin-only: manually trigger the 7-day temporary image cleanup.

NOTE: Annotation logic is NOT modified here.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.image import Image
from app.models.user import User
from app.dependencies.auth import get_current_user, require_admin
from app.services.lifecycle_service import promote_to_permanent, run_cleanup

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request schemas (lifecycle-specific)
# ---------------------------------------------------------------------------

class PromoteRequest(BaseModel):
    """Optional explicit YOLO TXT path for promotion. If omitted, the service
    looks for yolo_label_path on the latest annotation for this image."""
    yolo_txt_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/images/{image_id}/promote")
def promote_image(
    image_id: str,
    body: PromoteRequest = PromoteRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Promote an image from temporary → permanent storage.

    Conditions checked inside the service:
    1. Temporary image file exists.
    2. A YOLO TXT file is available (from annotation or explicit path).
    3. YOLO TXT passes format validation.
    4. Permanent files are successfully written and verified.
    5. DB status updated to 'permanent' only after all conditions pass.
    6. Temporary files deleted only after DB commit.
    """
    # Authorization: only owner or admin
    image = db.query(Image).filter(Image.image_id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    if image.user_id != current_user.user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to promote this image",
        )

    result = promote_to_permanent(
        db=db,
        image_id=image_id,
        yolo_txt_path=body.yolo_txt_path,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result["message"],
        )

    return result


@router.get("/images/{image_id}/status")
def get_lifecycle_status(
    image_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the full lifecycle state of an image."""
    image = db.query(Image).filter(Image.image_id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    if image.user_id != current_user.user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this image",
        )

    return {
        "image_id": image.image_id,
        "status": image.status,
        "storage_type": image.storage_type,
        "temp_s3_path": image.temp_s3_path,
        "permanent_s3_path": image.permanent_s3_path,
        "yolo_txt_path": image.yolo_txt_path,
        "uploaded_at": str(image.uploaded_at) if image.uploaded_at else None,
        "temporary_expires_at": str(image.temporary_expires_at) if image.temporary_expires_at else None,
        "annotated_at": str(image.annotated_at) if image.annotated_at else None,
        "converted_at": str(image.converted_at) if image.converted_at else None,
        "permanent_at": str(image.permanent_at) if image.permanent_at else None,
    }


@router.post("/cleanup")
def trigger_cleanup(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin-only: manually trigger the expired temporary image cleanup.

    Finds all temporary images whose temporary_expires_at < now and removes
    their physical files, marking them as 'expired_cleaned' in the DB.
    Permanent images are NEVER affected.
    """
    stats = run_cleanup(db)
    logger.info(
        "Manual cleanup triggered by admin %s | stats=%s",
        admin.user_id, stats,
    )
    return {
        "message": "Cleanup completed",
        "cleaned": stats["cleaned"],
        "errors": stats["errors"],
        "skipped": stats["skipped"],
    }
