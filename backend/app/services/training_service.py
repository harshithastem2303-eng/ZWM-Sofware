from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.training import TrainingJob
from app.config import settings


def check_dataset_readiness(db: Session):
    """
    Training readiness against the TOTAL number of training-eligible images
    across all active categories (v1.1.0). There is no per-category threshold.

    ready == total eligible images >= next cumulative milestone
             (last locked snapshot milestone + configured threshold).

    Returns (ready: bool, category_stats: list). Per-category entries are
    informational only and do not affect readiness.
    """
    from app.services.training_dataset_service import (
        get_training_progress,
        get_eligible_counts_by_category,
    )

    categories = db.query(Category).filter(Category.is_active.is_(True)).all()
    if not categories:
        return False, []

    progress = get_training_progress(db)
    eligible_by_cat = get_eligible_counts_by_category(db)

    stats = []
    for cat in categories:
        stats.append({
            "category_id": cat.category_id,
            "class_name": cat.class_name,
            "class_code": cat.class_code,
            "yolo_class_index": cat.yolo_class_index,
            "validated_count": cat.validated_count or 0,
            "training_eligible_count": eligible_by_cat.get(cat.category_id, 0),
            "threshold": progress["threshold"],
            # Readiness is global (total-based), never per category.
            "ready": progress["ready"],
        })

    return progress["ready"], stats


def trigger_training_job(db: Session, version: str, class_counts: dict = None):
    """
    Create a new training job record and queue it for execution.
    Allows admin manual trigger or automated trigger.
    """
    new_job = TrainingJob(
        version=version,
        class_counts=class_counts,
        status="queued",
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return new_job