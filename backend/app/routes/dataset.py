from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.category import Category
from app.models.image import Image
from app.models.user import User
from app.dependencies.auth import require_admin
from app.config import settings

router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "dataset"}


@router.get("/stats")
def get_dataset_stats(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Per-category validated image counts and overall dataset statistics."""
    categories = db.query(Category).all()
    threshold = settings.CATEGORY_VALIDATED_THRESHOLD

    category_stats = []
    for cat in categories:
        count = cat.validated_count or 0
        category_stats.append({
            "category_id": cat.category_id,
            "class_name": cat.class_name,
            "class_code": cat.class_code,
            "validated_count": count,
            "threshold": threshold,
            "ready": count >= threshold,
        })

    total_images = db.query(Image).count()
    validated_images = db.query(Image).filter(Image.is_validated == True, Image.status == "approved").count()
    pending_images = db.query(Image).filter(Image.status == "uploaded", Image.is_validated == False).count()

    return {
        "total_images": total_images,
        "validated_images": validated_images,
        "pending_images": pending_images,
        "threshold": threshold,
        "categories": category_stats,
    }


@router.get("/readiness")
def check_dataset_readiness(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Check if all categories have enough validated images to trigger training."""
    from app.services.training_service import check_dataset_readiness as check_ready

    ready, stats = check_ready(db)
    return {
        "ready": ready,
        "threshold": settings.CATEGORY_VALIDATED_THRESHOLD,
        "categories": stats,
    }
