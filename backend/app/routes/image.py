"""
Image routes.

POST /upload           – Upload and validate a new image
GET  /                 – List images for the current user
GET  /{image_id}       – Get a single image record
DELETE /{image_id}     – Delete an image (only non-approved)

Storage structure:
  uploads/temporary/{user_id}/{image_id}{ext}   ← initial save location
  uploads/permanent/{user_id}/{image_id}{ext}   ← after promotion
"""
import logging
import os
import uuid
import shutil
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.image import Image
from app.models.user import User
from app.dependencies.auth import get_current_user
from app.config import settings
from app.services.image_validator import validate_image

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "image"}


@router.post("/upload", status_code=status.HTTP_201_CREATED)
def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload and validate an image.

    The image is stored in temporary storage (uploads/temporary/{user_id}/).
    temporary_expires_at is set to now + TEMP_EXPIRY_DAYS (default 7 days).
    Status is set to 'uploaded' (backward-compatible).
    """
    # Validate extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Use: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Generate IDs and paths
    image_id = str(uuid.uuid4())
    safe_filename = f"{image_id}{ext}"
    user_id = current_user.user_id

    # Temporary storage directory: uploads/temporary/{user_id}/
    temp_dir = os.path.join(settings.UPLOAD_FOLDER, "temporary", user_id)
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, safe_filename)

    # Save file to disk
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Run image validation pipeline
    validation_result = validate_image(file_path)
    img_status = "uploaded" if validation_result["valid"] else "rejected"

    # Compute expiry
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.TEMP_EXPIRY_DAYS)

    # Create DB record
    new_image = Image(
        image_id=image_id,
        user_id=user_id,
        original_filename=file.filename or safe_filename,
        storage_type="local",
        temp_s3_path=file_path,
        status=img_status,
        temporary_expires_at=expires_at,
    )
    db.add(new_image)
    db.commit()
    db.refresh(new_image)

    # Remove file from disk if validation failed
    if not validation_result["valid"] and os.path.exists(file_path):
        os.remove(file_path)

    logger.info(
        "IMAGE_UPLOADED | image_id=%s | user_id=%s | status=%s | expires_at=%s",
        image_id, user_id, img_status, expires_at.isoformat(),
    )

    return {
        "image_id": new_image.image_id,
        "original_filename": new_image.original_filename,
        "status": new_image.status,
        "validation": validation_result,
    }


@router.get("/")
def list_images(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    images = (
        db.query(Image)
        .filter(Image.user_id == current_user.user_id)
        .order_by(Image.uploaded_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    results = [
        {
            "image_id": img.image_id,
            "original_filename": img.original_filename,
            "status": img.status,
            "is_validated": img.is_validated,
            "credits_awarded": img.credits_awarded,
            "uploaded_at": str(img.uploaded_at) if img.uploaded_at else None,
        }
        for img in images
    ]
    return {"images": results, "count": len(results)}


@router.get("/{image_id}")
def get_image(
    image_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    image = db.query(Image).filter(Image.image_id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Owner or admin
    if image.user_id != current_user.user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to view this image")

    return {
        "image_id": image.image_id,
        "user_id": image.user_id,
        "original_filename": image.original_filename,
        "storage_type": image.storage_type,
        "status": image.status,
        "is_validated": image.is_validated,
        "reward_given": image.reward_given,
        "credits_awarded": image.credits_awarded,
        "uploaded_at": str(image.uploaded_at) if image.uploaded_at else None,
        "validated_at": str(image.validated_at) if image.validated_at else None,
        "temporary_expires_at": str(image.temporary_expires_at) if image.temporary_expires_at else None,
        "annotated_at": str(image.annotated_at) if image.annotated_at else None,
        "converted_at": str(image.converted_at) if image.converted_at else None,
        "permanent_at": str(image.permanent_at) if image.permanent_at else None,
        "yolo_txt_path": image.yolo_txt_path,
    }


@router.delete("/{image_id}")
def delete_image(
    image_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    image = db.query(Image).filter(Image.image_id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    if image.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this image")

    if image.status == "approved":
        raise HTTPException(status_code=400, detail="Cannot delete an approved image")

    # Delete temporary file from disk
    if image.temp_s3_path and os.path.exists(image.temp_s3_path):
        os.remove(image.temp_s3_path)
    # Delete permanent file from disk (if any)
    if image.permanent_s3_path and os.path.exists(image.permanent_s3_path):
        os.remove(image.permanent_s3_path)

    db.delete(image)
    db.commit()
    return {"message": "Image deleted successfully"}


@router.get("/{image_id}/file")
def get_image_file(
    image_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Serve the raw image file securely to authenticated owner or admin."""
    image = db.query(Image).filter(Image.image_id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Authorize: owner or admin
    if image.user_id != current_user.user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to access this image file")

    path = image.permanent_s3_path or image.temp_s3_path
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Image file not found on disk")

    from fastapi.responses import FileResponse
    return FileResponse(path)

