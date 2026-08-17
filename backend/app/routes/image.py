import os
import uuid
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.image import Image
from app.models.user import User
from app.dependencies.auth import get_current_user
from app.config import settings
from app.services.image_validator import validate_image

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
    # Validate extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Use: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Ensure upload directory exists
    upload_dir = settings.UPLOAD_FOLDER
    os.makedirs(upload_dir, exist_ok=True)

    # Save file to disk
    image_id = str(uuid.uuid4())
    safe_filename = f"{image_id}{ext}"
    file_path = os.path.join(upload_dir, safe_filename)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Run image validation pipeline
    validation_result = validate_image(file_path)
    img_status = "uploaded" if validation_result["valid"] else "rejected"

    # Create DB record
    new_image = Image(
        image_id=image_id,
        user_id=current_user.user_id,
        original_filename=file.filename or safe_filename,
        temp_s3_path=file_path,
        status=img_status,
    )
    db.add(new_image)
    db.commit()
    db.refresh(new_image)

    # Remove file from disk if validation failed
    if not validation_result["valid"] and os.path.exists(file_path):
        os.remove(file_path)

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
        "status": image.status,
        "is_validated": image.is_validated,
        "reward_given": image.reward_given,
        "credits_awarded": image.credits_awarded,
        "uploaded_at": str(image.uploaded_at) if image.uploaded_at else None,
        "validated_at": str(image.validated_at) if image.validated_at else None,
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

    # Delete file from disk
    if image.temp_s3_path and os.path.exists(image.temp_s3_path):
        os.remove(image.temp_s3_path)
    if image.permanent_s3_path and os.path.exists(image.permanent_s3_path):
        os.remove(image.permanent_s3_path)

    db.delete(image)
    db.commit()
    return {"message": "Image deleted successfully"}
