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


from typing import Optional
from fastapi import Form
from app.models.category import Category
from app.services.image_validator import validate_image, validate_ai_category_match


@router.post("/upload", status_code=status.HTTP_201_CREATED)
def upload_image(
    file: UploadFile = File(...),
    selected_category_id: Optional[int] = Form(None),
    category_id: Optional[int] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload and validate an image against user-selected admin category.

    - Validates image extension, corrupt file check, and format.
    - Validates category exists and is active.
    - Runs independent AI prediction vs user-selected class validation:
      - High confidence match (>=80%) -> AUTO_ACCEPTED ('approved')
      - Low confidence / Mismatch / Unsupported class -> PENDING_ADMIN_REVIEW ('pending_admin_review')
    """
    # Check Platform Maintenance Mode from SystemSetting
    from app.models.setting import SystemSetting
    sys_setting = db.query(SystemSetting).filter(SystemSetting.id == 1).first()
    if sys_setting and sys_setting.maintenance_mode:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Platform Maintenance Mode is currently active. Uploads are temporarily locked during maintenance."
        )

    # Validate extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Use: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    target_category_id = selected_category_id if selected_category_id is not None else category_id
    selected_category = None

    if target_category_id is not None:
        selected_category = db.query(Category).filter(Category.category_id == target_category_id).first()
        if not selected_category:
            raise HTTPException(status_code=400, detail=f"Category ID {target_category_id} not found.")
        if not selected_category.is_active:
            raise HTTPException(status_code=400, detail=f"Category '{selected_category.class_name}' is currently inactive.")

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

    # 1. Run basic image format/corruption checks
    base_validation = validate_image(file_path)
    if not base_validation["valid"]:
        if os.path.exists(file_path):
            os.remove(file_path)
        reason_key = base_validation.get("reason", "")
        checks = base_validation.get("checks", {})
        err_msg = f"Image validation failed: {reason_key}"
        if reason_key in checks and isinstance(checks[reason_key], dict) and "message" in checks[reason_key]:
            err_msg = checks[reason_key]["message"]
        raise HTTPException(status_code=400, detail=err_msg)

    # 2. Run AI Class Match Validation
    ai_predicted_cat = None
    ai_conf_score = None
    val_result = "UNSPECIFIED_CATEGORY"
    val_status = "uploaded"
    val_reason = "No category selected."
    is_val = False

    if selected_category:
        ai_eval = validate_ai_category_match(file_path, selected_category.class_name)
        ai_predicted_cat = ai_eval.get("predicted_category")
        ai_conf_score = ai_eval.get("confidence")
        val_result = ai_eval.get("validation_result")
        val_status = ai_eval.get("status")
        val_reason = ai_eval.get("reason")
        is_val = ai_eval.get("is_validated", False)

    # Compute expiry
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.TEMP_EXPIRY_DAYS)

    # Award credits if auto-accepted
    credits = 0
    reward_given = False
    if val_status == "approved":
        credits = 10
        reward_given = True
        current_user.reward_points = (current_user.reward_points or 0) + 10
        current_user.image_count = (current_user.image_count or 0) + 1

    # Create DB record
    new_image = Image(
        image_id=image_id,
        user_id=user_id,
        original_filename=file.filename or safe_filename,
        storage_type="local",
        temp_s3_path=file_path,
        selected_category_id=selected_category.category_id if selected_category else None,
        ai_predicted_category=ai_predicted_cat,
        ai_confidence_score=ai_conf_score,
        validation_result=val_result,
        validation_reason=val_reason,
        status=val_status,
        is_validated=is_val,
        reward_given=reward_given,
        credits_awarded=credits,
        temporary_expires_at=expires_at,
    )
    db.add(new_image)
    db.commit()
    db.refresh(new_image)

    return {
        "message": "Image uploaded successfully",
        "image_id": image_id,
        "status": new_image.status,
        "validation": base_validation,
        "validation_result": new_image.validation_result,
        "validation_reason": new_image.validation_reason,
        "ai_predicted_category": new_image.ai_predicted_category,
        "ai_confidence_score": new_image.ai_confidence_score,
        "selected_category_id": new_image.selected_category_id,
        "selected_category_name": selected_category.class_name if selected_category else None,
        "credits_awarded": new_image.credits_awarded,
        "uploaded_at": str(new_image.uploaded_at) if new_image.uploaded_at else None,
    }


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

