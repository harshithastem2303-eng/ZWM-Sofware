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

    from app.models.setting import SystemSetting
    sys_setting = db.query(SystemSetting).filter(SystemSetting.id == 1).first()
    threshold = sys_setting.auto_retrain_count if sys_setting else settings.CATEGORY_VALIDATED_THRESHOLD

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