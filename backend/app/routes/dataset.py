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
    categories = db.query(Category).all()
    from app.models.setting import SystemSetting
    sys_setting = db.query(SystemSetting).filter(SystemSetting.id == 1).first()
    threshold = sys_setting.auto_retrain_count if sys_setting else settings.CATEGORY_VALIDATED_THRESHOLD

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
    """Total-image readiness for the next cumulative training milestone."""
    from app.services.training_service import check_dataset_readiness as check_ready
    from app.services.training_dataset_service import get_training_progress

    ready, stats = check_ready(db)
    progress = get_training_progress(db)
    return {
        "ready": ready,
        "threshold": progress["threshold"],
        "total_training_eligible_images": progress["total_training_eligible_images"],
        "last_milestone": progress["last_milestone"],
        "next_milestone": progress["next_milestone"],
        "remaining_to_next_milestone": progress["remaining_to_next_milestone"],
        "images_since_last_milestone": progress["images_since_last_milestone"],
        "snapshot_count": progress["snapshot_count"],
        "categories": stats,
    }


@router.get("/snapshots")
def list_training_snapshots(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List locked cumulative training snapshots (read-only)."""
    from app.models.training import TrainingSnapshot
    from app.services.training_dataset_service import snapshot_to_dict

    snapshots = db.query(TrainingSnapshot).order_by(TrainingSnapshot.version).all()
    return {"snapshots": [snapshot_to_dict(s) for s in snapshots], "count": len(snapshots)}


@router.post("/snapshots/reconcile")
def reconcile_snapshots(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Idempotently lock any reached-but-missing milestone snapshots (recovery path)."""
    from app.services.training_dataset_service import reconcile_training_snapshots, snapshot_to_dict

    from app.services.training_pipeline_service import dispatch_pending_training_jobs

    created = reconcile_training_snapshots(db)
    payload = {"created": [snapshot_to_dict(s) for s in created], "count": len(created)}
    payload["dispatch"] = dispatch_pending_training_jobs(db)
    return payload


@router.get("/snapshots/{snapshot_id}/images")
def get_training_snapshot_images(
    snapshot_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Exact, ordered image IDs locked into a snapshot."""
    from fastapi import HTTPException
    from app.models.training import TrainingSnapshot
    from app.services.training_dataset_service import get_snapshot_image_ids, snapshot_to_dict

    snapshot = db.query(TrainingSnapshot).filter(TrainingSnapshot.snapshot_id == snapshot_id).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {**snapshot_to_dict(snapshot), "image_ids": get_snapshot_image_ids(db, snapshot_id)}
