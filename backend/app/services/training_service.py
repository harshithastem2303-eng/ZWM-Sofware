from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.training import TrainingJob
from app.config import settings


def check_dataset_readiness(db: Session):
    """
    Check if all categories have enough validated images to meet the threshold.
    Returns (ready: bool, category_stats: list).
    """
    categories = db.query(Category).all()

    if not categories:
        return False, []

    threshold = settings.CATEGORY_VALIDATED_THRESHOLD
    stats = []
    for cat in categories:
        count = cat.validated_count or 0
        stats.append({
            "category_id": cat.category_id,
            "class_name": cat.class_name,
            "class_code": cat.class_code,
            "validated_count": count,
            "threshold": threshold,
            "ready": count >= threshold,
        })

    ready = all(s["ready"] for s in stats)
    return ready, stats


def trigger_training_job(db: Session, version: str, class_counts: dict = None):
    """
    Create a new training job record. Does NOT actually run training —
    that requires external infrastructure (GPU worker, dataset on disk, etc.).
    Returns the created TrainingJob or None if dataset is not ready.
    """
    ready, _ = check_dataset_readiness(db)

    if not ready:
        return None

    new_job = TrainingJob(
        version=version,
        class_counts=class_counts,
        status="queued",
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return new_job